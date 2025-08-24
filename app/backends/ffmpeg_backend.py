from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable, cast

import ffmpeg

from app.utils import Timer, log_exception, ensure_folder


@runtime_checkable
class _Filterable(Protocol):
    """Minimal protocol for ffmpeg-python streams used here."""

    def filter(self, name: str, *args, **kwargs) -> "_Filterable": ...
    def filter_multi_output(self, name: str, *args, **kwargs) -> list["_Filterable"]: ...


class FClip:
    """
    Thin, chainable wrapper around ffmpeg streams.
    Represents a still image (looped) + audio track(s).
    """

    v: Optional[_Filterable]
    a: Optional[_Filterable]

    def __init__(
        self,
        v: Optional[_Filterable] = None,
        a: Optional[_Filterable] = None,
        image_path: Optional[Path] = None,
        a_paths: Optional[list[Path]] = None,
        offset_y: Optional[int] = None,
        viewport_h: Optional[int] = None,
        viewport_w: Optional[int] = None,
    ):
        self.v = v
        self.a = a
        self.image_path = Path(image_path) if image_path else None
        self.a_paths = [Path(p) for p in a_paths] if a_paths else []
        self.offset_y = offset_y
        self.viewport_h = viewport_h
        self.viewport_w = viewport_w


    @classmethod
    def from_image_audio(
        cls,
        image_path: str | Path,
        audio_path: str | list[str] | list[Path],
        *,
        loop: int = 1,
        fps: int = 24,
        max_h: int = 1920,
        max_w: Optional[int] = 1080,
        sar: int = 1,
        pix_fmt: str = "yuv420p",
        verbose: bool = True,
        capture_stderr: bool = True,
        capture_stdout: bool = False,
        offset_y: int = 0,           
        viewport_h: int | None = None,  # (defaults to max_h when None)
        viewport_w: int | None = None,  # (defaults to max_w when None)
        side_margin_px: Optional[int] = None,
    ) -> "FClip":
        """
        Build a clip from a still image + one or more audio files.
        """
        try:
            # normalize paths
            img_path = Path(image_path)
            if isinstance(audio_path, (str, Path)):
                audio_paths = [Path(audio_path)]
            else:
                audio_paths = [Path(p) for p in audio_path]

            # Decide scale args
            if max_w and max_h:
                scale_args = [f"min({max_w},iw)", f"min({max_h},ih)"]
            elif max_w:
                scale_args = [f"min({max_w},iw)", -1]
            else:
                scale_args = [-1, f"min({max_h},ih)"]

            v = (
                ffmpeg
                .input(str(img_path), loop=loop, framerate=fps)
                .filter("scale", *scale_args)
                .filter("format", pix_fmt)
                .filter("setsar", sar)
            )

            a = ffmpeg.input(str(audio_paths[0]))

            return cls(
                cast(_Filterable, v),
                cast(_Filterable, a),
                image_path=img_path,
                a_paths=audio_paths,
                offset_y=offset_y,         
                viewport_h=viewport_h,
                viewport_w=viewport_w,
            )

        except Exception:
            log_exception(f"FClip.from_image_audio(image={image_path}, audio={audio_path})")
            raise


    def _need_video(self) -> _Filterable:
        if self.v is None:
            raise ValueError("Video stream is not initialized on this FClip.")
        return self.v

    def _need_audio(self) -> _Filterable:
        if self.a is None:
            raise ValueError("Audio stream is not initialized on this FClip.")
        return self.a

    def crop(self, w: int, h: int, x: int, y: int) -> "FClip":
        v = self._need_video()
        self.v = v.filter("crop", w, h, x, y)
        return self

    def fade_in(self, duration: float) -> "FClip":
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

    @staticmethod
    def get_audio_duration(path: Path) -> float:
        """Return duration (in seconds) of an audio file using ffprobe."""
        probe = ffmpeg.probe(str(path))
        for stream in probe["streams"]:
            if stream["codec_type"] == "audio":
                return float(stream["duration"])
        raise RuntimeError(f"Could not determine duration of {path}")

    def render(
        self,
        out_path: str | Path,
        *,
        fps: int = 24,
        vcodec: str = "h264_nvenc",
        preset: str = "p5",
        tune: str = "hq",
        cq: int = 23,
        pix_fmt: str = "yuv420p",
        acodec: str = "aac",
        audio_bitrate: str = "192k",
        overwrite: bool = True,
        verbose: bool = True,
        capture_stderr: bool = False,   # show ffmpeg stderr by default for easier debugging
        capture_stdout: bool = False,
        show_progress: bool = False,
        side_margin_px: int = None,
        keep_segments: bool = False
    ) -> Path:
        """
        Encode each (image+audio) pair as its own segment with per-clip:
        1) scale to inner width (viewport_w - side margins)
        2) optional pad to full viewport (pillarbox)
        3) crop vertical window at offset_y of viewport_h
        Then concat all segments with stream copy.
        """
        out_path = Path(out_path)
        ensure_folder(out_path.parent)

        # pull global viewport + margins from the first clip (they're all the same)
        if not self.clips:
            raise ValueError("Timeline has no clips to render.")

        # We read each clip's own viewport size, but side padding is uniform
        first = self.clips[0]
        full_w = int(first.viewport_w or 1080)
        full_h = int(first.viewport_h or 1920)
        side_margin_px = side_margin_px if side_margin_px else 0

        inner_w = full_w - (2 * side_margin_px)
        if inner_w <= 0:
            raise ValueError(f"side_margin_px too large: inner_w would be {inner_w}")

        seg_files: list[Path] = []
        concat_list = out_path.parent / "files.txt"

        try:
            # build each segment independently
            for i, clip in enumerate(self.clips):
                if not clip.image_path or not clip.a_paths:
                    raise ValueError("FClip missing image_path or a_paths")

                oy = int(clip.offset_y or 0)
                vw = int(clip.viewport_w or full_w)
                vh = int(clip.viewport_h or full_h)

                seg_out = out_path.parent / f"seg_{i}.mp4"

                # 1) scale to the inner width (content area) – height follows aspect
                v = (
                    ffmpeg
                    .input(str(clip.image_path), loop=1, framerate=fps)
                    .filter("scale", inner_w, -1)
                )

                # 2) crop a viewport-tall slice at offset_y using the inner width (no margins yet)
                v = v.filter("crop", inner_w, vh, 0, oy)

                # 3) pad horizontally to full viewport width with side margins (height is now exactly vh)
                if side_margin_px > 0:
                    v = v.filter(
                        "pad",
                        full_w,         # target width (inner + margins)
                        vh,             # target height (same as cropped viewport)
                        side_margin_px, # x offset = left margin
                        0,              # y offset = no top pad
                        "black"
                    )

                # 4) pixel format last
                v = v.filter("format", pix_fmt)

                a = ffmpeg.input(str(clip.a_paths[0]))

                (
                    ffmpeg
                    .output(
                        v, a, str(seg_out),
                        vcodec=vcodec, preset=preset, tune=tune, cq=cq,
                        pix_fmt=pix_fmt, shortest=None, r=fps,
                        acodec=acodec, audio_bitrate=audio_bitrate
                    )
                    .overwrite_output()
                    .run(
                        quiet=False,                # keep logs on while stabilizing
                        capture_stderr=capture_stderr,
                        capture_stdout=capture_stdout
                    )
                )

                # For debuggin, log audio duration
                try:
                    dur = self.get_audio_duration(seg_out)
                    if verbose:
                        print(f"[SEG {i:02d}] {seg_out.name} audio ~ {dur:.2f}s")
                except Exception:
                    if verbose:
                        print(f"[SEG {i:02d}] {seg_out.name} audio duration probe failed")

                # Finally concat the segment
                seg_files.append(seg_out)

                # ---- filter-concat (re-encode once) ----
                inputs = [ffmpeg.input(str(p)) for p in seg_files]
                vstreams = [inp.video for inp in inputs]
                astreams = [inp.audio for inp in inputs]

                vcat = ffmpeg.filter(vstreams, 'concat', n=len(seg_files), v=1, a=0)
                acat = ffmpeg.filter(astreams, 'concat', n=len(seg_files), v=0, a=1)

                (
                    ffmpeg
                    .output(
                        vcat, acat, str(out_path),
                        vcodec=vcodec, preset=preset, tune=tune, cq=cq,
                        pix_fmt=pix_fmt, r=fps,
                        acodec=acodec, audio_bitrate=audio_bitrate
                    )
                    .overwrite_output()
                    .run(
                        quiet=not verbose,
                        capture_stderr=capture_stderr,
                        capture_stdout=capture_stdout
                    )
                )




            # cleanup temporary files unless told to keep
            if not keep_segments:
                for p in seg_files:
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                try:
                    concat_list.unlink(missing_ok=True)
                except Exception:
                    pass

            return out_path

        except Exception:
            log_exception(f"Timeline.render({out_path})")
            # attempt cleanup on failure (best-effort)
            if not keep_segments:
                for p in seg_files:
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                try:
                    concat_list.unlink(missing_ok=True)
                except Exception:
                    pass
            raise
