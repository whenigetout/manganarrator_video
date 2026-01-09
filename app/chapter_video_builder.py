from pathlib import Path
import json, re
from typing import List, Dict, Any, Tuple, Optional
from app.video_runner import VideoRunner
from app.config import VideoConfig
from typing import Optional
import subprocess, shlex
import app.models.domain as d
import app.models.api as a
import mn_contracts.ocr as o
import app.models.exceptions as ex
import mn_contracts.pcc_backend as p
import app.utils as utils
from app.backends.ffmpeg_backend import FClip, Timeline

class ChapterVideoBuilder:
    def __init__(self, config: VideoConfig, resolution=(1080,1920), safe_margin=200):
        self.runner = VideoRunner(config)
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

            result = d.OCRImg_preview(
                **img.model_dump(),
                frame_size=frame_size,
                side_margin_px=settings.side_margin_px,
                frame_padding_top=settings.first_dialog_top_padding,
                img_scale=img_scale,
                dialogue_lines=dlg_previews
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

            result = d.OCRRun_preview(
                **ocrrun.model_dump(),
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
    ) -> d.ClipSpec:
        """
        Lowest-level materialization:
        DialogueLine_preview → ClipSpec
        """

        return d.ClipSpec(
            image_path=img_path,
            audio_paths=[
                dlg.audio_ref.resolve(media_root=Path(self.config.media_root))
            ],
            pan_steps=[
                d.PanStep(
                    dlg_id=dlg.id,
                    offset_y=dlg.preview_frame.y1
                )
            ],
            viewport_w=frame_size.w,
            viewport_h=frame_size.h,
        )

    def build_ocrimg_video(
        self,
        img_preview: d.OCRImg_preview,
    ) -> d.TimelineSpec:
        """
        OCRImg_preview → TimelineSpec
        (concatenation of DialogueLine clips)
        """

        img_path = img_preview.image_info.image_ref.resolve(
            media_root=Path(self.config.media_root)
        )

        clips: list[d.ClipSpec] = []

        for dlg in img_preview.dialogue_lines:
            clip = self.build_dialogueline_video(
                dlg,
                img_path=img_path,
                frame_size=img_preview.frame_size,
            )
            clips.append(clip)

        return d.TimelineSpec(clips=clips)

    def build_ocrrun_video(
        self,
        ocrrun_preview: d.OCRRun_preview,
        *,
        out_path: Path,
    ) -> Path:
        """
        OCRRun_preview → final rendered video
        """

        all_clips: list[d.ClipSpec] = []

        for img_preview in ocrrun_preview.images:
            img_timeline = self.build_ocrimg_video(img_preview)
            all_clips.extend(img_timeline.clips)

        timeline_spec = d.TimelineSpec(clips=all_clips)

        runner = Timeline(clips=)

        return timeline.ren(
            timeline,
            out_path=out_path,
            cfg=self.config,
        )
