from pathlib import Path
import json, re
from typing import List, Dict, Any, Tuple, Optional
from app.config import VideoConfig
from typing import Optional
import subprocess, shlex
import app.models.domain as d
import app.models.api as a
import mn_contracts.ocr as o
import app.models.exceptions as ex
import mn_contracts.pcc_backend as p
import app.utils as utils
from app.backends.ffmpeg_backend.clip import FClip
from app.backends.ffmpeg_backend.concat import concat_clips, concat_files
import math

class ChapterVideoBuilder:
    def __init__(self, config: VideoConfig, resolution=(1080,1920), safe_margin=200):
        self.res_w, self.res_h = resolution
        self.safe_margin = safe_margin
        self.config = config

    def _make_silence(self, out_wav: Path, seconds: float, sr: int = 48000) -> Path:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = f'ffmpeg -y -f lavfi -i anullsrc=r={sr}:cl=stereo -t {seconds} "{out_wav}"'
        subprocess.run(shlex.split(cmd), check=True)
        return out_wav

    def segments_from_img(
            self,
            img_info: o.ImageInfo,
            image_scale: float,
            dlg_by_id: Dict[int, d.VideoDialogueLine],
            top_padding: int,
            bottom_padding: int,
            viewport_h: int
    ) -> List[d.Segment]:
        
        img_h_scaled = img_info.image_height * image_scale
        total_segment_count = math.ceil(img_h_scaled / viewport_h)
        segments: List[d.Segment] = []
        start_y1 = 0
        for idx in range(total_segment_count):
            start_y2 = start_y1 + viewport_h
            def assigned_dialogues():
                result = []
                for dlg in dlg_by_id.values():
                    def should_dlg_be_in_segment() -> bool:
                        bbox = dlg.original_bbox
                        bbox_y1_scaled, bbox_y2_scaled = bbox.y1 * image_scale, bbox.y2 * image_scale

                        # very rare, almost imppractical edge case:
                        if bbox_y2_scaled - bbox_y1_scaled > (viewport_h - top_padding - bottom_padding):
                            raise ex.BuildVideoError(
                                f"Dialogue bbox taller than usable viewport. "
                                f"bbox_height={bbox_y2_scaled - bbox_y1_scaled}, "
                                f"viewport_h={viewport_h}"
                            )

                        top_ok = bbox_y1_scaled >= start_y1 + top_padding
                        bottom_ok = bbox_y2_scaled <= start_y2 - bottom_padding

                        if top_ok and bottom_ok:
                            return True

                        if not top_ok and bottom_ok:
                            # split at top
                            if bbox_y2_scaled - start_y1 >= (bbox_y2_scaled - bbox_y1_scaled) / 2:
                                return True

                        if top_ok and not bottom_ok:
                            # split at bottom
                            if start_y2 - bbox_y1_scaled >= (bbox_y2_scaled - bbox_y1_scaled) / 2:
                                return True
                            
                        return False

                    if should_dlg_be_in_segment():
                        result.append(dlg.id)
                
                return result

            segment = d.Segment(
                segment_id=idx + 1, # ids start from 1, just being consistent with image and dialogueline ids which also start from 1
                base_y1=start_y1,
                base_y2=start_y2,
                image_info=img_info,
                video_dialogue_ids=assigned_dialogues()
            )

            segments.append(segment)
            start_y1 += viewport_h
        
        return segments


    def segment_to_rendered_segment(
            self,
            segment: d.Segment,
            dlg_by_id: Dict[int, d.VideoDialogueLine],
            image_scale: float,
            top_padding: int,
            side_margin: int,
            bottom_padding: int,
            viewport_w: int,
            viewport_h: int,
            img_info: o.ImageInfo
            ) -> d.RenderedSegment:
        crop_y1, crop_y2 = segment.base_y1, segment.base_y2
        if len(segment.video_dialogue_ids) > 0:
            # first dialogue
            first_dlg_id = segment.video_dialogue_ids[0]
            first_dlg_bbox = dlg_by_id[first_dlg_id].original_bbox
            first_bbox_y1_scaled = first_dlg_bbox.y1 * image_scale
            if first_bbox_y1_scaled < crop_y1 + top_padding:
                # stretch top edge above the first dlg
                crop_y1 = first_bbox_y1_scaled - top_padding

            # last dialgoue
            last_dlg_id = segment.video_dialogue_ids[-1]
            last_dlg_bbox = dlg_by_id[last_dlg_id].original_bbox
            last_bbox_y2_scaled = last_dlg_bbox.y2 * image_scale
            if last_bbox_y2_scaled > crop_y2 - bottom_padding:
                # stretch bottom edge below last dlg
                crop_y2 = last_bbox_y2_scaled + bottom_padding

        base_y1, base_y2 = segment.base_y1, segment.base_y2

        top_conflict = crop_y1 < base_y1
        bottom_conflict = crop_y2 > base_y2

        render_height = crop_y2 - crop_y1

        if render_height > viewport_h:
            # both edges conflicting
            # If both top and bottom overflow, we prioritize the first dialogue
            # and clamp the opposite edge. This avoids padding or distortion.

            if top_conflict and bottom_conflict:
                # prioritize first dialogue (top)
                crop_y2 = crop_y1 + viewport_h
            elif top_conflict:
                crop_y2 = crop_y1 + viewport_h
            elif bottom_conflict:
                crop_y1 = crop_y2 - viewport_h
            else:
                # should never happen, but be defensive
                raise ex.BuildVideoError(
                    f"Render span overflow without edge conflict: {render_height} > {viewport_h}"
                )
            
        # At this point, crop_y1 / crop_y2 represent the *desired* visible region
        # in scaled-image coordinates.
        #
        # They are allowed to go out of bounds intentionally:
        #   - crop_y1 < 0  => we want black space above the image
        #   - crop_y2 > img_h_scaled => we want black space below the image
        #
        # ffmpeg does NOT allow out-of-bounds crop coordinates, so we normalize
        # this by conceptually embedding the image inside a padded canvas.
        # The padding amounts below represent real black space that will be
        # materialized via ffmpeg's pad filter.


        img_h_scaled = img_info.image_height * image_scale
        empty_space_top = max(0, -crop_y1)
        empty_space_bottom = max(0, crop_y2 - img_h_scaled)
        padded_img_h = img_h_scaled + empty_space_top + empty_space_bottom
        crop_y1_padded = crop_y1 + empty_space_top
        crop_y2_padded = crop_y2 + empty_space_top

        # Shift crop coordinates into the padded image coordinate system.
        # After this transformation:
        #   - crop_y1_padded >= 0
        #   - crop_y2_padded <= padded image height
        #
        # This guarantees the crop box is always valid for ffmpeg,
        # while preserving the original visual intent exactly.


        render_span = d.SegmentRenderSpan(
            crop_y1=int(crop_y1_padded),
            crop_y2=int(crop_y2_padded),
            render_height=int(crop_y2_padded - crop_y1_padded),
            image_scale=image_scale,
            empty_space_top=int(empty_space_top),
            empty_space_bottom=int(empty_space_bottom),
            empty_space_left=side_margin,
            empty_space_right=side_margin
        )
            
        return d.RenderedSegment(
            segment=segment,
            render_span=render_span,
            viewport_size=d.Size(
                w=viewport_w,
                h=viewport_h
            )
        )

    def rendered_segment_to_preview(self, 
                                    rend_seg: d.RenderedSegment, 
                                    dlg_by_id: Dict[int, d.VideoDialogueLine],
                                    default_silent_clip_duration: float = 3
                                    ) -> d.SegmentPreview:
        assigned_dialogue_lines = list(map(
            lambda dlg_id: dlg_by_id[dlg_id],
            rend_seg.segment.video_dialogue_ids
        ))
        duration = default_silent_clip_duration
        if len(assigned_dialogue_lines) > 0:
            audio_paths = [dlg.audio_ref.resolve(Path(self.config.media_root)) 
                            for dlg in assigned_dialogue_lines]
            total_audio_duration = sum(list(map(
                utils.get_audio_duration,
                audio_paths
            )))
            duration = total_audio_duration

        return d.SegmentPreview(
            rendered_segment=rend_seg,
            duration=duration,
            video_dialogue_lines=assigned_dialogue_lines
        )
    
    def build_img_preview(
            self,
            render_config: d.RenderConfig,
            img_info: o.ImageInfo,
            run_id: str,
            image_id: int,
            dlg_by_id: Dict[int, d.VideoDialogueLine]
    ) -> d.ImagePreview:
        
        viewport_w, viewport_h = render_config.viewport_w, render_config.viewport_h
        content_w = render_config.viewport_w - 2 * render_config.side_margin_px
        image_scale = content_w / img_info.image_width

        # split img into segments

        img_segments = self.segments_from_img(
            img_info=img_info,
            image_scale=image_scale,
            dlg_by_id=dlg_by_id,
            top_padding=render_config.first_dialog_top_padding,
            bottom_padding=render_config.last_dialog_bottom_padding,
            viewport_h=viewport_h
        )
        
        img_rendered_segments = [self.segment_to_rendered_segment(
                                        segment=seg,
                                        dlg_by_id=dlg_by_id,
                                        image_scale=image_scale,
                                        top_padding=render_config.first_dialog_top_padding,
                                        bottom_padding=render_config.last_dialog_bottom_padding,
                                        viewport_w=viewport_w,
                                        viewport_h=viewport_h,
                                        img_info=img_info,
                                        side_margin=render_config.side_margin_px
                                    ) for seg in img_segments]
        img_base_timeline = [self.rendered_segment_to_preview(
                                    rend_seg=rend_seg,
                                    dlg_by_id=dlg_by_id,
                                    default_silent_clip_duration=render_config.default_silent_clip_duration
                                ) 
                                for rend_seg in img_rendered_segments]
        
        return d.ImagePreview(
            run_id=run_id,
            image_id=image_id,
            base_timeline=img_base_timeline
        )

    def build_all_img_previews(
            self,
            build_vid_input: d.BuildVideoInput
    ) -> List[d.ImagePreview]:
        try:
            ocrrun, render_config = build_vid_input.ocr_run, build_vid_input.render_config
            segment_previews: List[d.ImagePreview] = []
            for img in ocrrun.images:
                img_info = img.image_info
                dlg_by_id = utils.build_video_dialogues_for_image(
                    run_id=ocrrun.run_id,
                    img=img,
                    media_root=self.config.media_root
                )
                img_preview = self.build_img_preview(
                    render_config=render_config,
                    img_info=img_info,
                    run_id=ocrrun.run_id,
                    image_id=img.image_id,
                    dlg_by_id=dlg_by_id
                )
                segment_previews.append(img_preview)
            return segment_previews
        except Exception as e:
            raise ex.BuildVideoError(str(e)) from e


    def build_video_from_ocrrun(
        self,
        build_vid_input: d.BuildVideoInput,
    ) -> Path:
        """
        Build the final video by:
        - generating preview (geometry + timing)
        - rendering many small temp clips (dialogue-level)
        - concatenating via stream copy (no re-encode)
        """

        ocrrun = build_vid_input.ocr_run
        render_config = build_vid_input.render_config

        # 1. Build preview (single source of truth)
        video_preview = d.VideoPreview(
            run_id=ocrrun.run_id,
            image_previews=self.build_all_img_previews(build_vid_input),
        )

        # 2. Resolve temp root (same folder as OCR JSON)
        ocr_json_path = Path(ocrrun.ocr_json_file.resolve(Path(self.config.media_root)))
        tmp_root = ocr_json_path.parent / "video_tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)

        image_level_videos: list[Path] = []

        # 3. Iterate preview structure
        for img_idx, img_prev in enumerate(video_preview.image_previews, start=1):
            img_temp_files: list[Path] = []
            img_dir = tmp_root / f"img_{img_idx:03d}"
            img_dir.mkdir(exist_ok=True)

            for seg_idx, seg_preview in enumerate(img_prev.base_timeline, start=1):
                seg_dir = img_dir / f"seg_{seg_idx:03d}"
                seg_dir.mkdir(exist_ok=True)

                rend = seg_preview.rendered_segment
                span = rend.render_span
                vp = rend.viewport_size

                # --- build base visual clip (no audio yet) ---
                img_path = Path(rend.segment.image_info.image_ref.resolve(Path(self.config.media_root)))

                base_clip = (
                    FClip.image(img_path, fps=render_config.fps)
                    .scale(w=vp.w, h=None)
                    .pad(
                        w=render_config.viewport_w,
                        h=int(
                            (rend.segment.image_info.image_height * span.image_scale)
                            + span.empty_space_top
                            + span.empty_space_bottom
                        ),
                        x=span.empty_space_left,
                        y=span.empty_space_top,
                    )
                    .crop(
                        w=render_config.viewport_w,
                        h=render_config.viewport_h,
                        x=0,
                        y=span.crop_y1,
                    )
                    .set_fps(render_config.fps)
                    .format(render_config.pix_fmt)
                )

                # --- case A: no dialogues → one silent clip ---
                if not seg_preview.video_dialogue_lines:
                    out_path = seg_dir / "silent.mp4"

                    clip = (
                        base_clip
                        .ensure_audio_track(
                            duration=seg_preview.duration,
                            sample_rate=44100,
                        )
                    )

                    clip.output(
                        out_path,
                        vcodec=render_config.vcodec,
                        acodec=render_config.acodec,
                        audio_bitrate=render_config.audio_bitrate,
                        pix_fmt=render_config.pix_fmt,
                        verbose=render_config.verbose,
                    )

                    img_temp_files.append(out_path)
                    continue

                # --- case B: one clip per dialogue ---
                for dlg_idx, dlg in enumerate(seg_preview.video_dialogue_lines, start=1):
                    out_path = seg_dir / f"dlg_{dlg_idx:03d}_id_{dlg.id}.mp4"

                    audio_path = Path(dlg.audio_ref.resolve(Path(self.config.media_root)))
                    audio_duration = utils.get_audio_duration(audio_path)

                    clip = (
                        base_clip
                        .with_audio(audio_path)
                        .ensure_video_track(
                            duration=audio_duration,
                            width=vp.w,
                            height=vp.h,
                        )
                    )

                    clip.output(
                        out_path,
                        vcodec=render_config.vcodec,
                        acodec=render_config.acodec,
                        audio_bitrate=render_config.audio_bitrate,
                        pix_fmt=render_config.pix_fmt,
                        verbose=render_config.verbose,
                    )

                    img_temp_files.append(out_path)

            img_out = img_dir / f"img_{img_idx:03d}.mp4"

            if not img_temp_files:
                raise ex.BuildVideoError(f"No clips produced for image {img_idx}")

            concat_files(
                paths=img_temp_files,
                out_path=img_out,
                overwrite=True,
                verbose=render_config.verbose,
            )

            image_level_videos.append(img_out)


        # 4. Final concat (stream copy)
        final_out = tmp_root.parent / f"{ocrrun.run_id}_final.mp4"

        concat_files(
            paths=image_level_videos,
            out_path=final_out,
            overwrite=True,
            verbose=render_config.verbose,
        )

        return final_out
