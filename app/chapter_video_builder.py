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

    def build_dialogue_line_preview(
            self,
            dlg: o.DialogueLine,
            run_id: str,
            img_ref: o.MediaRef,
            img_size: d.Size,
            frame_size: d.Size,
            img_scale: float,
            frame_top_padding: int = 0,
            prev_preview: Optional[d.DialogueLine_preview] = None
    ) -> d.DialogueLine_preview:
        """
        Compute DialogueLine preview for ocr img dialogue line
        """
        try:
            # error if invalid bbox 
            if dlg.original_bbox.y1 < 0 or dlg.original_bbox.y1 > img_size.h:
                raise ex.InvalidInputError(f"Invalid bbox for dlgId: {dlg.id} with text: {dlg.text}")

            bbox_scaled = dlg.original_bbox.scaled(img_scale)
            y1 = prev_preview.preview_frame.y1 if prev_preview else 0
            y1 -= frame_top_padding
            y2 = y1 + frame_size.h

            # bbox is inside the frame/viewport
            if y1 <= bbox_scaled.y1 and y2 >= bbox_scaled.y2:
                pass
            # bbox falls outside the frame/viewport
            else:
                y1 = bbox_scaled.y1 - frame_top_padding
                y2 = y1 + frame_size.h

            # edge case: last bbox is too close to the bottom
            if y2 > img_size.h * img_scale:
                y2 = img_size.h * img_scale
                y1 = y2 - frame_size.h

            # latest audio ref
            latest_audio_ref = p.latest_tts_audio_ref(
                run_id=run_id,
                dlg_id=dlg.id,
                img_ref=img_ref,
                media_root=self.config.media_root
            )

            # audio duration
            audio_path = latest_audio_ref.resolve(media_root=Path(self.config.media_root))
            latest_audio_duration = utils.get_audio_duration(path=audio_path)

            preview = d.DialogueLine_preview(
                **dlg.model_dump(),
                preview_frame=d.Frame(
                    x1=0,
                    y1=int(y1),
                    x2=frame_size.w,
                    y2=int(y2),
                ),
                audio_ref=latest_audio_ref,
                duration=latest_audio_duration
            )

            return preview
        except:
            raise ex.PreviewError

    def build_ocrimg_preview(
        self,
        run_id: str,
        img: o.OCRImage,
        settings: d.RenderConfig,
    ) -> d.OCRImg_preview:
        """
        Compute preview frames for each dialogue in an image.
        Pure function: no IO, no ffmpeg.
        """
        try:
            img_w, img_h = img.image_info.image_width, img.image_info.image_height
            img_size = d.Size(
                w=img_w, 
                h=img_h
            )

            frame_size = d.Size(
                w=settings.viewport_w - 2 * settings.side_margin_px,
                h=settings.viewport_h
            )

            # scale image to viewport width (same as video logic)
            img_scale = frame_size.w / img_size.w

            dlg_previews: List[d.DialogueLine_preview] = []

            prev_preview = None
            for dlg in img.dialogue_lines:
                prev_preview = self.build_dialogue_line_preview(
                    dlg=dlg,
                    run_id=run_id,
                    img_ref=img.image_info.image_ref,
                    img_size=img_size,
                    frame_size=frame_size,
                    img_scale=img_scale,
                    frame_top_padding=settings.first_dialog_top_padding,
                    prev_preview=prev_preview
                )

                dlg_previews.append(prev_preview)

            base = img.model_dump(exclude={"dialogue_lines"})

            result = d.OCRImg_preview(
                **base,
                frame_size=frame_size,
                side_margin_px=settings.side_margin_px,
                frame_padding_top=settings.first_dialog_top_padding,
                img_scale=img_scale,
                dialogue_lines=dlg_previews,
            )

            return result
        except:
            raise ex.PreviewError
        
    def build_ocrrun_preview(
        self,
        ocrrun: o.OCRRun,
        settings: d.RenderConfig,
    ) -> d.OCRRun_preview:
        """
        Compute preview frames for each dialogue in an image.
        Pure function: no IO, no ffmpeg.
        """
        try:
            img_previews: List[d.OCRImg_preview] = []

            for img in ocrrun.images:
                preview = self.build_ocrimg_preview(
                    run_id=ocrrun.run_id,
                    img=img,
                    settings=settings
                )
                img_previews.append(preview)

            base = ocrrun.model_dump(exclude={"images"})

            result = d.OCRRun_preview(
                **base,
                images=img_previews
            )
            return result
        except:
            raise ex.PreviewError

    def build_dialogueline_video(
        self,
        dlg: d.DialogueLine_preview,
        *,
        img_path: Path,
        frame_size: d.Size,
        settings: d.RenderConfig,
        out_path: Path,
    ) -> Path:
        """
        Render ONE dialogue line to ONE mp4 (hard FFmpeg boundary).
        This is NVENC-safe and memory-bounded.
        """

        audio_path = dlg.audio_ref.resolve(
            media_root=Path(self.config.media_root)
        )

        pf = dlg.preview_frame

        clip = (
            FClip.image(img_path)
            .scale(w=frame_size.w)
            .crop(
                w=frame_size.w,
                h=frame_size.h,
                x=0,
                y=pf.y1,
            )
            .with_audio(audio_path)
        )

        # 🔴 CRITICAL FIX: reset audio PTS to start at 0
        if not clip.a:
            raise
        clip.a = clip.a.filter("asetpts", "PTS-STARTPTS")

        clip.output(
            out_path,
            vcodec=settings.vcodec,
            pix_fmt=settings.pix_fmt,
            acodec=settings.acodec,
            audio_bitrate=settings.audio_bitrate,
            verbose=settings.verbose,
            overwrite=True,
        )

        return out_path

    def build_ocrimg_video(
        self,
        img_preview: d.OCRImg_preview,
        *,
        tmp_dir: Path,
        img_index: int,
        settings: d.RenderConfig,
    ) -> Path:
        """
        OCRImg_preview → ONE image-level mp4
        Internally renders ONE mp4 per dialogue (safe),
        then concats them cheaply.
        """

        img_path = img_preview.image_info.image_ref.resolve(
            media_root=Path(self.config.media_root)
        )

        dialogue_mp4s: list[Path] = []

        for j, dlg in enumerate(img_preview.dialogue_lines):
            dlg_out = tmp_dir / f"img_{img_preview.image_id}_dlg_{dlg.id}.mp4"

            self.build_dialogueline_video(
                dlg,
                img_path=img_path,
                frame_size=img_preview.frame_size,
                settings=settings,
                out_path=dlg_out,
            )

            dialogue_mp4s.append(dlg_out)

        # Cheap concat (NO re-encode)
        img_out = tmp_dir / f"img_{img_preview.image_id}.mp4"

        concat_files(
            dialogue_mp4s,
            img_out,
            overwrite=True,
            verbose=settings.verbose,
        )

        return img_out

    def build_ocrrun_video(
        self,
        ocrrun: o.OCRRun,
        *,
        settings: d.RenderConfig
    ) -> o.MediaRef:
        try:
            ocrrun_preview = self.build_ocrrun_preview(
                ocrrun=ocrrun,
                settings=settings
            )

            ocr_json_path = ocrrun.ocr_json_file.resolve(Path(self.config.media_root))
            out_dir = ocr_json_path.parent

            tmp_dir = out_dir.parent / "_tmp_imgs"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            image_mp4s: list[Path] = []

            for i, img_preview in enumerate(ocrrun_preview.images):
                img_mp4 = self.build_ocrimg_video(
                    img_preview,
                    tmp_dir=tmp_dir,
                    img_index=i,
                    settings=settings,
                )
                image_mp4s.append(img_mp4)

            # Final concat (NO filters, NO re-encode)
            out_path = out_dir / "narrated_video.mp4"
            concat_files(
                image_mp4s,
                out_path,
                overwrite=True,
                verbose=settings.verbose,
            )

            video_ref = o.MediaRef(
                namespace=o.MediaNamespace.OUTPUTS,
                path=(out_path.relative_to(Path(self.config.media_root) / o.MediaNamespace.OUTPUTS.value)).as_posix()
            )
            return video_ref
        except:
            raise ex.BuildVideoError(f"Failed to build video for runid: {ocrrun.run_id}")

    def build_img_segment_preview(
            self,
            img: o.OCRImage,
            run_id: str
    ):
        try:
            # split img into segments
            pass
        except:
            raise ex.BuildVideoError

    def build_segment_previews(
            self,
            input: d.BuildSegmentPreviewInput
    ) -> List[d.ImageSegmentPreview]:
        try:
            ocrrun, render_config = input.ocr_run, input.render_config
            segment_previews: List[d.ImageSegmentPreview] = []
            for img in ocrrun.images:
                # img_segment_previews = build_img_segment_preview()
                def build_img_segment_preview():
                    # split img into segments
                    def segments_from_img():
                        img_info = img.image_info
                        viewport_w, viewport_h = render_config.viewport_w - 2 * render_config.side_margin_px, render_config.viewport_h
                        scale = viewport_w / img_info.image_width
                        img_h_scaled = img_info.image_height * scale
                        total_segment_count = math.ceil(img_h_scaled // viewport_h)
                        segments: List[d.Segment] = []
                        start_y1 = 0
                        for idx in range(1, total_segment_count + 1):
                            start_y2 = start_y1 + viewport_h
                            def assign_dialogues():
                                all_dlgs = img.dialogue_lines
                                assigned_dlgs = []
                                for dlg in all_dlgs:
                                    def should_dlg_be_in_segment() -> bool:
                                        bbox = dlg.original_bbox
                                        bbox_y1_scaled, bbox_y2_scaled = bbox.y1 * scale, bbox.y2 * scale

                                        # very rare, almost imppractical edge case:
                                        if bbox_y2_scaled - bbox_y1_scaled > (viewport_h -render_config.first_dialog_top_padding -render_config.last_dialog_bottom_padding):
                                            raise ex.BuildVideoError("The impractical edge case happened, the bbox/speech bubble is LARGER than the viewport size")
                                        
                                        # bbox completely inside segment
                                        def is_bbox_completely_inside_segment():
                                            top_ok = bbox_y1_scaled >= start_y1 + render_config.first_dialog_top_padding
                                            bottom_ok = bbox_y2_scaled <= start_y2 - render_config.last_dialog_bottom_padding

                                            return top_ok and bottom_ok
                                        if is_bbox_completely_inside_segment():
                                            return True

                                        # it's either split at the top edge or the bottom edge
                                        def is_bbox_split_at_top():
                                            top_ok = bbox_y1_scaled >= start_y1 + render_config.first_dialog_top_padding
                                            bottom_ok = bbox_y2_scaled <= start_y2 - render_config.last_dialog_bottom_padding
                                            return not top_ok and bottom_ok
                                        
                                        def is_bbox_split_at_bottom():
                                            top_ok = bbox_y1_scaled >= start_y1 + render_config.first_dialog_top_padding
                                            bottom_ok = bbox_y2_scaled <= start_y2 - render_config.last_dialog_bottom_padding
                                            return top_ok and not bottom_ok
                                        
                                        if is_bbox_split_at_top():
                                            # if at least half of it is inside the segment, assign it
                                            # can ignore top/bottom padding for this decision
                                            if bbox_y2_scaled - start_y1 >= (bbox_y2_scaled - bbox_y1_scaled) / 2:
                                                return True

                                        if is_bbox_split_at_bottom():
                                            # if at least half of it is inside the segment, assign it
                                            # can ignore top/bottom padding for this decision
                                            if start_y2 - bbox_y1_scaled >= (bbox_y2_scaled - bbox_y1_scaled) / 2:
                                                return True
                                            
                                        return False

                                    if should_dlg_be_in_segment():
                                        assigned_dlgs.append(dlg.id)

                            start_y1 += viewport_h

                # segment_previews.append(*img_segment_previews)
            return segment_previews
        except:
            raise ex.BuildVideoError

    def build_video_from_ocrrun(
            self,
            input: d.BuildVideoInput
    ):
        try:
            pass
        except:
            raise ex.BuildVideoError
