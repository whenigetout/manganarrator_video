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
from mn_contracts import common as c
import app.utils as utils
from app.backends.ffmpeg_backend.clip import FClip
from app.backends.ffmpeg_backend.concat import concat_clips, concat_files
import math
from app.utils import (
    log,
    LogColor
)

class ChapterVideoBuilder:
    def __init__(self, config: VideoConfig, resolution=(1080,1920), safe_margin=200):
        self.res_w, self.res_h = resolution
        self.safe_margin = safe_margin
        self.config = config

    def _make_silence(self, out_wav: Path, seconds: float, sr: int) -> Path:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = f'ffmpeg -y -f lavfi -i anullsrc=r={sr}:cl=stereo -t {seconds} "{out_wav}"'
        subprocess.run(shlex.split(cmd), check=True)
        return out_wav

    def should_dlg_be_in_segment(
        self,
        dlg:d.VideoDialogueLine,
        image_scale: float,
        top_padding: int,
        bottom_padding: int,
        viewport_h: int,
        start_y1: int,
        start_y2: int
    ) -> bool:
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


    def assigned_dialogues(
        self,
        dlg_by_id: Dict[int, d.VideoDialogueLine],
        image_scale: float,
        top_padding: int,
        bottom_padding: int,
        viewport_h: int,
        start_y1: int,
        start_y2: int
    ):
        result = []
        for dlg in dlg_by_id.values():

            if self.should_dlg_be_in_segment(
                dlg=dlg,
                image_scale=image_scale,
                top_padding=top_padding,
                bottom_padding=bottom_padding,
                viewport_h=viewport_h,
                start_y1=start_y1,
                start_y2=start_y2
            ):
                result.append(dlg.id)
        
        return result


    def segments_from_img(
            self,
            img_info: o.ImageInfo,
            image_id: int,
            run_id: str,
            image_scale: float,
            dlg_by_id: Dict[int, d.VideoDialogueLine],
            top_padding: int,
            bottom_padding: int,
            viewport_h: int,
            scaled_h: int
    ) -> List[d.Segment]:
        
        img_h_scaled = scaled_h
        total_segment_count = math.ceil(img_h_scaled / viewport_h)
        segments: List[d.Segment] = []
        start_y1 = 0
        for idx in range(total_segment_count):
            start_y2 = start_y1 + viewport_h

            segment = d.Segment(
                segment_id=idx + 1, # ids start from 1, just being consistent with image and dialogueline ids which also start from 1
                image_id=image_id,
                run_id=run_id,
                base_y1=start_y1,
                base_y2=start_y2,
                image_info=img_info,
                video_dialogue_ids=self.assigned_dialogues(
                    dlg_by_id=dlg_by_id,
                    image_scale=image_scale,
                    top_padding=top_padding,
                    bottom_padding=bottom_padding,
                    viewport_h=viewport_h,
                    start_y1=start_y1,
                    start_y2=start_y2
                )
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
        img_info: o.ImageInfo,
        scaled_h: int
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


        img_h_scaled = scaled_h
        empty_space_top = max(0, -crop_y1)
        empty_space_bottom = max(0, crop_y2 - img_h_scaled)
        padded_img_h = img_h_scaled + empty_space_top + empty_space_bottom
        crop_y1_padded = crop_y1 + empty_space_top
        crop_y2_padded = crop_y2 + empty_space_top

        # clamp calculated crop values to prevent overflow bugs later
        crop_y1_padded = max(0, crop_y1_padded)
        crop_y2_padded = min(
            scaled_h + empty_space_top + empty_space_bottom,
            crop_y2_padded
        )

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

    def rendered_segment_to_preview(
        self, 
        rend_seg: d.RenderedSegment, 
        dlg_by_id: Dict[int, d.VideoDialogueLine],
        img_root: str | Path,
        default_silent_clip_duration: float = 3,
    ) -> d.SegmentPreview:
        segment_id = rend_seg.segment.segment_id

        # just a sanity check this is not a practical case
        if segment_id > 999:
            raise ValueError("Unexpected segment_id, video previews assume a max of 999 segments per image.")
        
        seg_folder_name = f"seg_{segment_id:03d}"
        
        seg_root = Path(img_root) / seg_folder_name

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
            video_dialogue_lines=assigned_dialogue_lines,
            out_dir_ref=c.build_media_Ref(
                namespace=o.MediaNamespace.OUTPUTS,
                path=Path(seg_root),
                media_root=self.config.media_root
            ),
            out_file_ref=c.build_media_Ref(
                namespace=o.MediaNamespace.OUTPUTS,
                path=Path(seg_root) / f"{seg_folder_name}.mp4",
                media_root=self.config.media_root
            )
        )
    
    def build_img_preview(
        self,
        render_config: d.RenderConfig,
        img_info: o.ImageInfo,
        run_id: str,
        image_id: int,
        dlg_by_id: Dict[int, d.VideoDialogueLine],
        tmp_root: str | Path
    ) -> d.ImagePreview:
        
        if image_id > 999:
            raise ValueError("Unexpected image_id, video previews assume a max of 999 images per ocrrun.")
        
        img_folder_name = f"img_{image_id:03d}"
        
        img_root = Path(tmp_root) / img_folder_name
        c.ensure_dir(img_root)
        
        viewport_w, viewport_h = render_config.viewport_w, render_config.viewport_h
        content_w = render_config.viewport_w - 2 * render_config.side_margin_px
        scaled_w = content_w  # exact, no rounding
        image_scale = scaled_w / img_info.image_width
        scaled_h = int(round(img_info.image_height * image_scale))

        # split img into segments

        img_segments = self.segments_from_img(
            img_info=img_info,
            image_id=image_id,
            run_id=run_id,
            image_scale=image_scale,
            dlg_by_id=dlg_by_id,
            top_padding=render_config.first_dialog_top_padding,
            bottom_padding=render_config.last_dialog_bottom_padding,
            viewport_h=viewport_h,
            scaled_h=scaled_h
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
                                    side_margin=render_config.side_margin_px,
                                    scaled_h=scaled_h
                                ) 
                                for seg in img_segments]
        img_base_timeline = [self.rendered_segment_to_preview(
                                rend_seg=rend_seg,
                                dlg_by_id=dlg_by_id,
                                img_root=img_root,
                                default_silent_clip_duration=render_config.default_silent_clip_duration
                            ) 
                            for rend_seg in img_rendered_segments]
        
        return d.ImagePreview(
            run_id=run_id,
            image_id=image_id,
            base_timeline=img_base_timeline,
            out_dir_ref=c.build_media_Ref(
                namespace=o.MediaNamespace.OUTPUTS,
                path=img_root,
                media_root=self.config.media_root
            ),
            out_file_ref=c.build_media_Ref(
                namespace=o.MediaNamespace.OUTPUTS,
                path=img_root / f"{img_folder_name}.mp4",
                media_root=self.config.media_root
            )
        )

    def build_all_img_previews(
            self,
            build_vid_input: d.BuildVideoInput,
            tmp_root: str | Path
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
                    dlg_by_id=dlg_by_id,
                    tmp_root=tmp_root
                )
                segment_previews.append(img_preview)
            return segment_previews
        except Exception as e:
            raise ex.BuildVideoError(str(e)) from e
        
    def build_video_preview(
        self,
        build_vid_input: d.BuildVideoInput
    ) -> d.VideoPreview:
        ocr_json_path = Path(build_vid_input.ocr_run.ocr_json_file.resolve(Path(self.config.media_root)))
        tmp_root = ocr_json_path.parent / "video_tmp"
        c.ensure_dir(tmp_root)
        vid_prw = d.VideoPreview(
            run_id=build_vid_input.ocr_run.run_id,
            image_previews=self.build_all_img_previews(build_vid_input, tmp_root=tmp_root),
            render_config=build_vid_input.render_config,
            out_dir_ref=c.build_media_Ref(
                namespace=o.MediaNamespace.OUTPUTS,
                path=tmp_root,
                media_root=self.config.media_root
            ),
            out_file_ref=c.build_media_Ref(
                namespace=o.MediaNamespace.OUTPUTS,
                path=tmp_root / "final.mp4",
                media_root=self.config.media_root
            )
        )

        prw_save_path = ocr_json_path.parent / "video_preview" / "preview.json"

        c.save_model_json(
            model=vid_prw,
            json_path=prw_save_path
        )

        print(f"✅ Preview JSON saved successfully.")

        return vid_prw
    
    def build_silent_seg_clip(
        self,
        seg_dir: Path,
        base_clip: FClip,
        seg_preview: d.SegmentPreview,
        render_config: d.RenderConfig
    ):
        silent_video_filename = f"{seg_dir.stem}_silent.mp4"
        seg_vid_out_path = seg_dir / silent_video_filename

        clip = (
            base_clip
            .ensure_audio_track(
                duration=seg_preview.duration,
                sample_rate=render_config.audio_default_sample_rate,
            )
        )

        clip.output(
            seg_vid_out_path,
            vcodec=render_config.vcodec,
            acodec=render_config.acodec,
            audio_bitrate=render_config.audio_bitrate,
            pix_fmt=render_config.pix_fmt,
            verbose=render_config.verbose,
        )

        return seg_vid_out_path
    
    def build_videoDialogueLine_video(
        self,
        dlg: d.VideoDialogueLine,
        dlg_idx:int,
        seg_dir: Path,
        base_clip: FClip,
        viewport_size: d.Size,
        render_config: d.RenderConfig
    ):
        try:
            log(f"🎧 Rendering dialogue clip {dlg_idx} (dlg_id={dlg.id})", LogColor.BLUE, 6)

            # sanity check, not a real case
            if dlg.id > 999:
                raise ValueError("Unexpected dialogue_id, video previews assume a max of 999 dialogue per segment.")
            
            videoDialogueLine_vid_out_path = seg_dir / f"dlg_{dlg_idx:03d}_id_{dlg.id}.mp4"

            audio_path = Path(dlg.audio_ref.resolve(Path(self.config.media_root)))
            audio_duration = utils.get_audio_duration(audio_path)

            clip = (
                base_clip
                .with_audio(audio_path)
                .ensure_video_track(
                    duration=audio_duration,
                    width=viewport_size.w,
                    height=viewport_size.h,
                )
            )
            log("▶️  Executing ffmpeg...", LogColor.YELLOW, 7)

            clip.output(
                videoDialogueLine_vid_out_path,
                vcodec=render_config.vcodec,
                acodec=render_config.acodec,
                audio_bitrate=render_config.audio_bitrate,
                pix_fmt=render_config.pix_fmt,
                verbose=render_config.verbose,
            )

            log(f"✅ Dialogue {dlg_idx} render complete", LogColor.GREEN, 7)

            return videoDialogueLine_vid_out_path
        except Exception as e:
            log(f"❌ FAILED at Dialogue {dlg_idx} (ID {dlg.id}) → {e}", LogColor.RED, 7)
            raise

    def build_seg_with_dlgs(
        self,
        seg_preview: d.SegmentPreview,
        seg_dir: Path,
        base_clip: FClip,
        render_config: d.RenderConfig,
        viewport_size: d.Size
    ):
        try:
            seg_video_out: Path
            seg_temp_files = []
            img_idx = seg_preview.rendered_segment.segment.image_id
            seg_idx = seg_preview.rendered_segment.segment.segment_id
            log(f"🎤 Segment {seg_idx}: Building dialogue clips...", LogColor.MAGENTA, 5)

            for dlg_idx, dlg in enumerate(seg_preview.video_dialogue_lines, start=1):
                log(f"🔊 Dialogue {dlg_idx} (ID {dlg.id})", LogColor.CYAN, 6)

                videoDialogueLine_video = self.build_videoDialogueLine_video(
                    dlg=dlg,
                    dlg_idx=dlg_idx,
                    seg_dir=seg_dir,
                    base_clip=base_clip,
                    viewport_size=viewport_size,
                    render_config=render_config
                )
                seg_temp_files.append(videoDialogueLine_video)

            if not seg_temp_files:
                raise ex.BuildVideoError(f"No clips produced for image {img_idx} segment {seg_idx}")
            
            seg_video_out = seg_dir / f"seg_{seg_idx:03d}_with_dialogues.mp4"

            concat_files(
                paths=seg_temp_files,
                out_path=seg_video_out,
                overwrite=True,
                verbose=render_config.verbose,
            )
            log(f"✅ Segment {seg_idx} dialogue concat complete", LogColor.GREEN, 6)
        
            return seg_video_out
        except Exception as e:
            log(f"❌ FAILED at dialogue-level in Segment {seg_idx}: {e}", LogColor.RED, 6)
            raise
    
    
    def build_img_segment_video(
        self,
        seg_preview: d.SegmentPreview,
        render_config: d.RenderConfig,
    ) -> o.MediaRef:
        try:
            img_idx = seg_preview.rendered_segment.segment.image_id
            seg_idx = seg_preview.rendered_segment.segment.segment_id

            log(f"🛠️  Rendering Segment {seg_idx} (Image {img_idx})", LogColor.CYAN, 4)

            seg_vid_out_path:Path
            seg_dir = seg_preview.out_dir_ref.resolve(self.config.media_root)
            c.ensure_dir(seg_dir)
            img_idx = seg_preview.rendered_segment.segment.image_id
            seg_idx = seg_preview.rendered_segment.segment.segment_id

            rend = seg_preview.rendered_segment
            span = rend.render_span
            vp = rend.viewport_size
            orig_w = rend.segment.image_info.image_width
            orig_h = rend.segment.image_info.image_height

            scaled_w = render_config.viewport_w - 2 * span.empty_space_left
            scaled_h = int(round(orig_h * span.image_scale))

            # --- encoder alignment layer ---
            if scaled_w % 2 != 0:
                scaled_w += 1

            if scaled_h % 2 != 0:
                scaled_h += 1

            # --- build base visual clip (no audio yet) ---
            img_path = Path(rend.segment.image_info.image_ref.resolve(Path(self.config.media_root)))
            log("⚙️  Preparing base visual clip...", LogColor.BLUE, 5)

            assert scaled_w + span.empty_space_left * 2 == render_config.viewport_w, \
                f"Width contract broken: scaled_w={scaled_w}, margin={span.empty_space_left}"

            print("DEBUG PAD:",
                "scaled_w=", scaled_w,
                "scaled_h=", scaled_h,
                "pad_w=", render_config.viewport_w,
                "pad_h=", scaled_h + span.empty_space_top + span.empty_space_bottom,
                "x=", span.empty_space_left)


            base_clip = (
                FClip.image(img_path, fps=render_config.fps)
                .scale(w=scaled_w, h=scaled_h)
                .pad(
                    w=render_config.viewport_w,
                    h = scaled_h + span.empty_space_top + span.empty_space_bottom,
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
                seg_vid_out_path = self.build_silent_seg_clip(
                    seg_dir=seg_dir,
                    base_clip=base_clip,
                    seg_preview=seg_preview,
                    render_config=render_config
                )
                log(f"✅ Segment {seg_idx} render complete", LogColor.GREEN, 5)

            else:
                # --- case B: one clip per dialogue ---

                seg_vid_out_path = self.build_seg_with_dlgs(
                    seg_preview=seg_preview,
                    seg_dir=seg_dir,
                    base_clip=base_clip,
                    render_config=render_config,
                    viewport_size=vp
                )

            return c.build_media_Ref(
                namespace=o.MediaNamespace.OUTPUTS,
                path=seg_vid_out_path,
                media_root=self.config.media_root
            )
        
        except Exception as e:
            log(f"❌ FAILED at Segment {seg_idx} (Image {img_idx}) → {e}", LogColor.RED, 5)
            raise

    def build_img_video(
        self,
        img_prw: d.ImagePreview,
        render_config: d.RenderConfig,
        regen_existing_clips: bool = False
    ) -> o.MediaRef:
        log(f"📂 Building video for Image {img_prw.image_id}", LogColor.GREEN, 3)

        img_temp_files: list[o.MediaRef] = []
        img_dir = img_prw.out_dir_ref.resolve(self.config.media_root)
        c.ensure_dir(img_dir)
        img_idx = img_prw.image_id

        for seg_preview in img_prw.base_timeline:
            seg_id = seg_preview.rendered_segment.segment.segment_id
            log(f"🎞️  Segment {seg_id}", LogColor.CYAN, 4)

            seg_vid_ref_from_preview = seg_preview.out_file_ref
            seg_vid_path = seg_vid_ref_from_preview.resolve(self.config.media_root)
            if seg_vid_path.exists() and not regen_existing_clips:
                img_temp_files.append(seg_vid_ref_from_preview)
            else:
                seg_vid_out = self.build_img_segment_video(
                    seg_preview=seg_preview,
                    render_config=render_config,
                )
                img_temp_files.append(seg_vid_out)

        img_out = img_dir / f"img_{img_idx:03d}.mp4"

        if not img_temp_files:
            raise ex.BuildVideoError(f"No clips produced for image {img_idx}")
        
        img_temp_file_paths = [
            ref.resolve(media_root=self.config.media_root) 
            for ref in img_temp_files
        ]

        log(f"🔗 Concatenating segments for Image {img_idx}", LogColor.YELLOW, 4)

        concat_files(
            paths=img_temp_file_paths,
            out_path=img_out,
            overwrite=True,
            verbose=render_config.verbose,
        )

        return c.build_media_Ref(
            namespace=o.MediaNamespace.OUTPUTS,
            path=img_out,
            media_root=self.config.media_root
        )


    def build_all_img_videos(
        self,
        video_preview: d.VideoPreview,
        regen_existing_clips: bool = False
    ) -> List[o.MediaRef]:
        image_level_videos: list[o.MediaRef] = []
        render_config = video_preview.render_config

        # 3. Iterate preview structure
        for img_idx, img_prw in enumerate(video_preview.image_previews, start=1):
            log(f"🖼️  Building image {img_prw.image_id}", LogColor.GREEN, 2)
    
            img_vid_ref_from_preview = img_prw.out_file_ref
            img_vid_path = img_vid_ref_from_preview.resolve(self.config.media_root)
            if img_vid_path.exists() and not regen_existing_clips:
                log(f"⏩ Skipping image {img_prw.image_id} (already exists)", LogColor.YELLOW, 3)
                image_level_videos.append(img_vid_ref_from_preview)
            else:
                img_out = self.build_img_video(
                    img_prw=img_prw,
                    render_config=video_preview.render_config,
                    regen_existing_clips=regen_existing_clips
                )
                image_level_videos.append(img_out)

        return image_level_videos

    def build_vid_from_video_prw(
        self,
        video_preview: d.VideoPreview,
        regen_existing_clips: bool = False
    ) -> o.MediaRef:
        
        log("📦 Building from VideoPreview...", LogColor.BLUE, 1)

        image_level_videos = self.build_all_img_videos(
            video_preview=video_preview,
            regen_existing_clips=regen_existing_clips
        )

        image_level_video_paths = [
            ref.resolve(media_root=self.config.media_root)
            for ref in image_level_videos
        ]

        # 4. Final concat (stream copy)
        final_out = video_preview.out_file_ref.resolve(media_root=self.config.media_root)
        log("🔗 Concatenating all image-level videos...", LogColor.YELLOW, 2)

        concat_files(
            paths=image_level_video_paths,
            out_path=final_out,
            overwrite=True,
            verbose=video_preview.render_config.verbose,
        )

        log("✅ Final concat done.", LogColor.GREEN, 2)

        final_video_ref = c.build_media_Ref(
            namespace=o.MediaNamespace.OUTPUTS,
            path=final_out,
            media_root=self.config.media_root
        )

        return final_video_ref

    def build_video_from_ocrrun(
        self,
        build_vid_input: d.BuildVideoInput,
        regen_existing_clips: bool = False,
        rebuild_preview: bool = False
    ) -> o.MediaRef:
        """
        Build the final video by:
        - generating preview (geometry + timing)
        - rendering many small temp clips (dialogue-level)
        - concatenating via stream copy (no re-encode)
        """
        try:

            log("🚀 Building FINAL VIDEO from OCRRun...", LogColor.MAGENTA)
            log(f"Run ID: {build_vid_input.ocr_run.run_id}", LogColor.MAGENTA, 1)

            # 1. Build preview (single source of truth)
            if rebuild_preview:
                video_preview = self.build_video_preview(build_vid_input=build_vid_input)
            else:
                ocr_json_path = build_vid_input.ocr_run.ocr_json_file.resolve(
                    media_root=self.config.media_root
                )
                preview_json_path = ocr_json_path.parent / "video_preview" / "preview.json"
                with preview_json_path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                video_preview: d.VideoPreview = d.VideoPreview.model_validate(raw)
            
            final_vid = self.build_vid_from_video_prw(
                video_preview=video_preview,
                regen_existing_clips=regen_existing_clips
            )

            log("🎉 Final video build complete!", LogColor.GREEN)
            return final_vid
        except Exception as e:
            log(f"❌ FAILED at top-level build: {e}", LogColor.RED)
            raise
