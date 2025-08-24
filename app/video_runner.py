from pathlib import Path
from datetime import datetime
import uuid
from typing import Optional

from app.backends.ffmpeg_backend import FClip, Timeline
from app.utils import Timer, log_exception, ensure_folder
from app.config import VideoConfig


class VideoRunner:
    def __init__(self, config: VideoConfig):
        """
        Initialize the VideoRunner with a config.
        """
        self.config = config
        self.output_dir = Path(config.output_folder)
        ensure_folder(self.output_dir)

    def _build_clips(
        self,
        image_path: str | Path,
        audio_files: list[str | Path],
        *,
        pan_plan: list[dict] | None = None,      # NEW
        loop: Optional[int] = None,
        fps: Optional[int] = None,
        max_h: Optional[int] = None,
        max_w: Optional[int] = None,
        sar: Optional[int] = None,
        pix_fmt: Optional[str] = None,
        side_margin_px: Optional[int] = None,
        verbose: Optional[bool] = None,
        capture_stderr: Optional[bool] = None,
        capture_stdout: Optional[bool] = None,
    ) -> list[FClip]:
        """
        Build a list of FClip objects: one image reused for all audio files.
        Now also applies per-dialogue crop offsets from pan_plan.
        """
        clips = []
        for idx, audio_path in enumerate(audio_files):
            try:
                offset_y = 0
                if pan_plan and idx < len(pan_plan):
                    offset_y = int(pan_plan[idx].get("offset", 0))

                clip = FClip.from_image_audio(
                    image_path=str(image_path),
                    audio_path=str(audio_path),
                    loop=loop if loop is not None else self.config.loop,
                    fps=fps if fps is not None else self.config.default_fps,
                    max_h=max_h if max_h is not None else self.config.max_height,
                    max_w=max_w if max_w is not None else self.config.max_width,
                    sar=sar if sar is not None else self.config.sar,
                    pix_fmt=pix_fmt if pix_fmt is not None else self.config.pix_fmt,
                    verbose=verbose if verbose is not None else self.config.verbose,
                    capture_stderr=capture_stderr if capture_stderr is not None else True,
                    capture_stdout=capture_stdout if capture_stdout is not None else False,
                    offset_y=offset_y,                               # NEW
                    viewport_h=max_h if max_h is not None else self.config.max_height,  # NEW
                    viewport_w=max_w if max_w is not None else self.config.max_width,   # NEW,
                    side_margin_px=side_margin_px
                )
                clips.append(clip)
            except Exception:
                log_exception(f"❌ Failed to build clip for audio={audio_path}")
                raise
        return clips


    def run_single_img(
        self,
        image_path: str | Path,
        audio_files: list[str | Path],
        run_id: str | None = None,
        out_filename: str = "final.mp4",
        *,
        pan_plan: list[dict] | None = None,
        output_dir: str | Path | None = None,
        side_margin_px: Optional[int] = None,
        # Overrides for backend parameters
        fps: Optional[int] = None,
        vcodec: Optional[str] = None,
        cq: Optional[int] = None,
        preset: Optional[str] = None,
        tune: Optional[str] = None,
        pix_fmt: Optional[str] = None,
        fade_s: Optional[float] = None,
        transition: Optional[str] = None,
        audio_fade: Optional[str] = None,
        overwrite: Optional[bool] = None,
        verbose: Optional[bool] = None,
        sar: Optional[int] = None,
        max_w: Optional[int] = None,
        max_h: Optional[int] = None,
        loop: Optional[int] = None,
        capture_stderr: Optional[bool] = None,
        capture_stdout: Optional[bool] = None,
        keep_segments: Optional[bool] = None
    ) -> dict:
        """
        Run the video pipeline with one image and multiple audio files.
        All parameters are configurable; explicit overrides take precedence.
        """
        # Generate run_id (still used for metadata if no explicit output_dir)
        if not run_id:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_id = f"video_{timestamp}_{uuid.uuid4().hex[:8]}"

        # Decide where to write: caller-provided output_dir OR default {config.output_folder}/{run_id}
        if output_dir is not None:
            out_dir = Path(output_dir)
        else:
            out_dir = self.output_dir / run_id
        ensure_folder(out_dir)

        # Build clips with overrides
        clips = self._build_clips(
            image_path,
            audio_files,
            pan_plan=pan_plan,
            loop=loop,
            fps=fps,
            max_h=max_h,
            max_w=max_w,
            sar=sar,
            pix_fmt=pix_fmt,
            side_margin_px=side_margin_px,
            verbose=verbose,
            capture_stderr=capture_stderr,
            capture_stdout=capture_stdout,
        )
        timeline = Timeline(clips)

        # Output path
        out_path = out_dir / out_filename

        # Merge overrides with config
        params = {
            "fps": fps if fps is not None else self.config.default_fps,
            "vcodec": vcodec if vcodec is not None else self.config.vcodec,
            "cq": cq if cq is not None else self.config.cq,
            "preset": preset if preset is not None else self.config.preset,
            "tune": tune if tune is not None else self.config.tune,
            "pix_fmt": pix_fmt if pix_fmt is not None else self.config.pix_fmt,
            # "fade_s": fade_s if fade_s is not None else self.config.fade_s,
            # "transition": transition if transition is not None else self.config.transition,
            # "audio_fade": audio_fade if audio_fade is not None else self.config.audio_fade,
            "overwrite": overwrite if overwrite is not None else self.config.overwrite,
            "verbose": verbose if verbose is not None else self.config.verbose,
            # "sar": sar if sar is not None else self.config.sar,
            # "max_w": max_w if max_w is not None else self.config.max_width,
            # "max_h": max_h if max_h is not None else self.config.max_height,
            "capture_stderr": capture_stderr if capture_stderr is not None else self.config.capture_stderr,
            "capture_stdout": capture_stdout if capture_stdout is not None else self.config.capture_stdout,
            "side_margin_px": side_margin_px if side_margin_px is not None else self.config.side_margin_px,
            "keep_segments": keep_segments if keep_segments is not None else self.config.keep_segments,
        }

        # Render
        with Timer(f"🎬 Rendering video to {out_path}"):
            result = timeline.render(out_path=out_path, **params)

        return {
            "runid": run_id,
            "output_file": str(result),
            "output_folder": str(out_dir),
            "num_audio": len(audio_files),
            "image": str(image_path)
        }
