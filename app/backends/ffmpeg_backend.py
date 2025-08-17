from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable, cast

import ffmpeg

from app.utils import Timer, log_exception, ensure_folder


@runtime_checkable
class _Filterable(Protocol):
    """Minimal protocol for ffmpeg-python streams used here."""
    def filter(self, name: str, *args, **kwargs) -> "_Filterable": ...
    # Note: ffmpeg-python returns objects you can re-filter; this is all we need.


class FClip:
    """
    Thin, chainable wrapper around ffmpeg streams.
    Represents a still image (looped) + audio track.
    """

    v: Optional[_Filterable]
    a: Optional[_Filterable]

    def __init__(self, v: Optional[_Filterable] = None, a: Optional[_Filterable] = None):
        self.v = v
        self.a = a

    @classmethod
    def from_image_audio(
        cls,
        image_path: str,
        audio_path: str,
        *,
        loop: int = 1,                 # 1 = loop image so it lasts as long as audio
        fps: int = 24,                 # video frame rate
        max_h: int = 1080,             # clamp max height for GPU codec compatibility
        max_w: Optional[int] = None,   # optional clamp for width
    ) -> "FClip":
        """
        Build a clip from a still image + audio file.
        Parameters are fully configurable so nothing is hardcoded.
        """
        try:
            # Decide scale arguments based on whether max_w is provided
            if max_w and max_h:
                scale_args = [f"min({max_w},iw)", f"min({max_h},ih)"]
            elif max_w:
                scale_args = [f"min({max_w},iw)", -1]
            else:
                scale_args = [-1, f"min({max_h},ih)"]

            # Build video stream (no setsar here anymore)
            v = (
                ffmpeg
                .input(image_path, loop=loop, framerate=fps)
                .filter("scale", *scale_args)
            )

            # Build audio stream
            a = ffmpeg.input(audio_path)

            return cls(cast(_Filterable, v), cast(_Filterable, a))

        except Exception:
            log_exception(f"FClip.from_image_audio(image={image_path}, audio={audio_path})")
            raise

    # ---- internal guards -----------------------------------------------------

    def _need_video(self) -> _Filterable:
        """Ensure video stream exists before applying video filters."""
        if self.v is None:
            raise ValueError("Video stream is not initialized on this FClip.")
        return self.v

    def _need_audio(self) -> _Filterable:
        """Ensure audio stream exists before applying audio filters."""
        if self.a is None:
            raise ValueError("Audio stream is not initialized on this FClip.")
        return self.a

    # ---- chainable ops -------------------------------------------------------

    def crop(self, w: int, h: int, x: int, y: int) -> "FClip":
        """Crop the video stream to a WxH window at (x,y)."""
        v = self._need_video()
        self.v = v.filter("crop", w, h, x, y)
        return self

    def fade_in(self, duration: float) -> "FClip":
        """Apply fade-in effect to both video and audio."""
        v = self._need_video()
        self.v = v.filter("fade", t="in", st=0, d=duration)
        if self.a is not None:
            self.a = self._need_audio().filter("afade", t="in", st=0, d=duration)
        return self


class Timeline:
    """
    Sequence of FClips that can be rendered with crossfades or hard cuts.
    """

    def __init__(self, clips: list[FClip]):
        if not clips:
            raise ValueError("Timeline requires at least one clip")
        self.clips = clips

    def render(
        self,
        out_path: str | Path,
        *,
        fps: int = 24,                 # output frame rate
        vcodec: str = "h264_nvenc",    # GPU-accelerated codec (default: NVIDIA)
        cq: int = 23,                  # constant quality value (lower = better)
        preset: str = "p5",            # codec speed/quality preset
        tune: str = "hq",              # tuning parameter (hq = high quality)
        pix_fmt: str = "yuv420p",      # pixel format
        fade_s: float = 0.5,           # crossfade duration in seconds
        transition: str = "fade",      # video transition type
        audio_fade: str = "acrossfade",# audio transition type
        overwrite: bool = True,        # whether to overwrite existing output
        verbose: bool = False,         # print ffmpeg logs
        sar: int = 1                   # 👈 configurable SAR, default 1
        
    ) -> Path:
        """
        Render timeline with ffmpeg. All encoding & transition params configurable.
        """
        out_path = Path(out_path)
        ensure_folder(out_path.parent)

        try:
            # Start with first clip
            v = self.clips[0]._need_video()
            a = self.clips[0]._need_audio()

            # Crossfade subsequent clips
            for i in range(1, len(self.clips)):
                v = ffmpeg.filter([v, self.clips[i]._need_video()],
                                  "xfade", transition=transition,
                                  duration=fade_s, offset=f"end-{fade_s}")
                a = ffmpeg.filter([a, self.clips[i]._need_audio()],
                                  audio_fade, d=fade_s)

            # ✅ Apply setsar ONCE at the end
            v = v.filter("format", pix_fmt).filter("setsar", sar)

            # Run ffmpeg
            with Timer(f"Rendering {out_path}"):
                (
                    ffmpeg
                    .output(v, a, str(out_path),
                            vcodec=vcodec, preset=preset, tune=tune,
                            cq=cq, pix_fmt=pix_fmt, r=fps)
                    .overwrite_output() if overwrite else ffmpeg.output(v, a, str(out_path))
                ).run(quiet=not verbose, capture_stderr=True, capture_stdout=False)

            return out_path

        except ffmpeg.Error as e:
            try:
                stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            except Exception:
                stderr = str(e)
            log_exception(f"ffmpeg failed while rendering {out_path}\n--- ffmpeg stderr ---\n{stderr}")
            raise RuntimeError(f"ffmpeg failed; see logs for details: {out_path}") from e
        except Exception:
            log_exception(f"Timeline.render({out_path})")
            raise
