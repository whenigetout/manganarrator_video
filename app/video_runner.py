from pathlib import Path
from datetime import datetime
import uuid

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

    def _build_clips(self, image_path: str | Path, audio_files: list[str | Path]) -> list[FClip]:
        """
        Build a list of FClip objects: one image reused for all audio files.
        """
        clips = []
        for audio_path in audio_files:
            try:
                clip = FClip.from_image_audio(
                    image_path=str(image_path),
                    audio_path=str(audio_path),
                    loop=self.config.loop,
                    fps=self.config.default_fps,
                    max_h=self.config.max_height,
                    max_w=self.config.max_width,
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
        out_filename: str = "final.mp4"
    ) -> dict:
        """
        Run the video pipeline with one image and multiple audio files.
        """
        # Generate run_id
        if not run_id:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_id = f"video_{timestamp}_{uuid.uuid4().hex[:8]}"

        out_dir = self.output_dir / run_id
        ensure_folder(out_dir)

        # Build clips
        clips = self._build_clips(image_path, audio_files)
        timeline = Timeline(clips)

        # Output path
        out_path = out_dir / out_filename

        # Render
        with Timer(f"🎬 Rendering video to {out_path}"):
            result = timeline.render(
                out_path=out_path,
                fps=self.config.default_fps,
                vcodec=self.config.vcodec,
                cq=self.config.cq,
                preset=self.config.preset,
                tune=self.config.tune,
                pix_fmt=self.config.pix_fmt,
                fade_s=self.config.fade_s,
                transition=self.config.transition,
                audio_fade=self.config.audio_fade,
                overwrite=self.config.overwrite,
                verbose=self.config.verbose,
            )

        return {
            "runid": run_id,
            "output_file": str(result),
            "output_folder": str(out_dir),
            "num_audio": len(audio_files),
            "image": str(image_path)
        }
