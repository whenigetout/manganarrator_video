from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable, Optional
import app.utils as utils

import ffmpeg

@runtime_checkable
class _Filterable(Protocol):
    """Minimal protocol for ffmpeg-python streams used here."""

    def filter(self, name: str, *args, **kwargs) -> "_Filterable": ...
    def filter_multi_output(self, name: str, *args, **kwargs) -> list["_Filterable"]: ...

class FClip:
    """
    Atomic, chainable wrapper around ffmpeg streams.

    Represents a single audiovisual segment.
    Can contain:
      - video only
      - audio only
      - video + audio

    NO domain meaning. NO OCR logic. NO policy.
    """

    def __init__(
        self,
        *,
        v: Optional[_Filterable] = None,
        a: Optional[_Filterable] = None,
        fps: int = 24,
    ):
        self.v = v
        self.a = a
        self.fps = fps

    # ----------------------------
    # Constructors
    # ----------------------------

    @staticmethod
    def image(path: str | Path, *, fps: int = 24, loop: int = 1) -> "FClip":
        v = ffmpeg.input(str(path), loop=loop, framerate=fps)
        return FClip(v=v, fps=fps)

    @staticmethod
    def audio(path: str | Path) -> "FClip":
        a = ffmpeg.input(str(path))
        return FClip(a=a)
    
    @staticmethod
    def from_file(path: Path) -> "FClip":
        """
        Create an FClip from an already-encoded media file
        (keeps both video and audio streams).
        """
        inp = ffmpeg.input(str(path))
        return FClip(
            v=inp.video,
            a=inp.audio,
            # DO NOT pass fps here
        )

    @staticmethod
    def empty(*, fps: int = 24) -> "FClip":
        """Useful as a base for synthetic clips later (text, color, etc)."""
        return FClip(fps=fps)
    
    @staticmethod
    def silence(duration: float, *, sample_rate: int = 44100) -> "FClip":
        a = ffmpeg.input(
            f"anullsrc=sample_rate={sample_rate}",
            format="lavfi",
            t=duration,
        )
        return FClip(a=a)


    @staticmethod
    def still(
        path: str | Path,
        *,
        duration: float,
        fps: int = 24,
    ) -> "FClip":
        v = ffmpeg.input(
            str(path),
            loop=1,
            framerate=fps,
            t=duration,
        )
        return FClip(v=v, fps=fps)

    @staticmethod
    def color(
        color: str,
        *,
        width: int,
        height: int,
        duration: float,
        fps: int = 24,
    ) -> "FClip":
        v = ffmpeg.input(
            f"color={color}:s={width}x{height}:d={duration}:r={fps}",
            format="lavfi",
        )
        return FClip(v=v, fps=fps)

    # ----------------------------
    # Guards
    # ----------------------------

    def _need_video(self) -> _Filterable:
        if self.v is None:
            raise RuntimeError("This operation requires a video stream.")
        return self.v

    def _need_audio(self) -> _Filterable:
        if self.a is None:
            raise RuntimeError("This operation requires an audio stream.")
        return self.a
    
    # ----------------------------
    # Fill in audio or video 
    # ----------------------------

    def ensure_audio_track(
        self,
        *,
        duration: float,
        sample_rate: int = 44100,
    ) -> "FClip":
        if self.a is None:
            self.a = FClip.silence(
                duration=duration,
                sample_rate=sample_rate,
            ).a
        return self


    def ensure_video_track(
        self,
        *,
        duration: float,
        width: int,
        height: int,
    ) -> "FClip":
        if self.v is None:
            self.v = FClip.color(
                "black",
                width=width,
                height=height,
                duration=duration,
                fps=self.fps,
            ).v
        return self



    # ----------------------------
    # Audio attachment
    # ----------------------------

    def with_audio(self, path: str | Path) -> "FClip":
        self.a = ffmpeg.input(str(path))
        return self

    def mute(self) -> "FClip":
        self.a = None
        return self

    # ----------------------------
    # Basic video transforms
    # ----------------------------

    def scale(self, w: int | None = None, h: int | None = None) -> "FClip":
        v = self._need_video()
        self.v = v.filter("scale", w or -1, h or -1)
        return self

    def crop(self, w: int, h: int, x: int, y: int) -> "FClip":
        v = self._need_video()
        self.v = v.filter("crop", w, h, x, y)
        return self

    def pad(
        self,
        w: int,
        h: int,
        x: int = 0,
        y: int = 0,
        color: str = "black",
    ) -> "FClip":
        '''
        Pad dimensions w, h MUST BE >= img dimensions 
        '''
        v = self._need_video()
        self.v = v.filter("pad", w, h, x, y, color)
        return self

    def set_fps(self, fps: int) -> "FClip":
        v = self._need_video()
        self.v = v.filter("fps", fps)
        self.fps = fps
        return self

    def format(self, pix_fmt: str) -> "FClip":
        v = self._need_video()
        self.v = v.filter("format", pix_fmt)
        return self

    # ----------------------------
    # Timing & animation
    # ----------------------------

    def trim(self, start: float | None = None, end: float | None = None) -> "FClip":
        if self.v:
            kwargs = {}
            if start is not None:
                kwargs["start"] = start
            if end is not None:
                kwargs["end"] = end

            self.v = (
                self.v
                .filter("trim", **kwargs)
                .filter("setpts", "PTS-STARTPTS")
            )

        if self.a:
            kwargs = {}
            if start is not None:
                kwargs["start"] = start
            if end is not None:
                kwargs["end"] = end

            self.a = (
                self.a
                .filter("atrim", **kwargs)
                .filter("asetpts", "PTS-STARTPTS")
            )

        return self


    def fade_in(self, duration: float) -> "FClip":
        if self.v:
            self.v = self.v.filter("fade", t="in", st=0, d=duration)
        if self.a:
            self.a = self.a.filter("afade", t="in", st=0, d=duration)
        return self

    def fade_out(self, duration: float, start: float) -> "FClip":
        if self.v:
            self.v = self.v.filter("fade", t="out", st=start, d=duration)
        if self.a:
            self.a = self.a.filter("afade", t="out", st=start, d=duration)
        return self

    def speed(self, factor: float) -> "FClip":
        if self.v:
            self.v = self.v.filter("setpts", f"PTS/{factor}")
        if self.a:
            self.a = self.a.filter("atempo", factor)
        return self

    # ----------------------------
    # Overlays / composition (basic)
    # ----------------------------

    def overlay(self, other: "FClip", x: int = 0, y: int = 0) -> "FClip":
        base = self._need_video()
        top = other._need_video()
        self.v = ffmpeg.overlay(base, top, x=x, y=y)
        return self

    # ----------------------------
    # Output helpers (no orchestration)
    # ----------------------------

    def output(
        self,
        path: str | Path,
        *,
        vcodec: str = "h264_nvenc",
        acodec: str = "aac",
        pix_fmt: str = "yuv420p",
        audio_bitrate: str = "192k",
        overwrite: bool = True,
        verbose: bool = True,
    ) -> None:
        path = Path(path)
        utils.ensure_folder(path=path.parent)

        if not self.v and not self.a:
            raise RuntimeError("Cannot output an empty clip.")

        kwargs = {}

        if self.v:
            kwargs.update({
                "vcodec": vcodec,
                "pix_fmt": pix_fmt,
                "r": self.fps,
            })

        if self.a:
            # normalize audio for AAC
            self.a = self.a.filter("aresample", 44100)

            kwargs.update({
                "acodec": acodec,
                "audio_bitrate": audio_bitrate,
            })

        if self.v and self.a:
            # Inject shortest into kwargs, NOT as a positional arg
            kwargs = dict(kwargs)
            kwargs["shortest"] = None # ✅ FLAG, no value

            print("=====================OUTPUT CALLED WITH:", path, kwargs)


            stream = ffmpeg.output(
                self.v,
                self.a,
                str(path),
                **kwargs
            )
        elif self.v:
            stream = ffmpeg.output(self.v, str(path), **kwargs)
        else:
            stream = ffmpeg.output(self.a, str(path), **kwargs)


        if overwrite:
            stream = stream.overwrite_output()

        stream.run(quiet=not verbose)

