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
        capture_stderr: bool = True,
        capture_stdout: bool = False,
        show_progress: bool = False,
    ) -> Path:
        """
        Fast render: encode each (image+audio) pair as its own segment with
        per-clip scale+crop, then concat with stream copy.
        """
        out_path = Path(out_path)
        ensure_folder(out_path.parent)

        try:
            seg_files: list[Path] = []

            for i, clip in enumerate(self.clips):
                if not clip.image_path or not clip.a_paths:
                    raise ValueError("FClip missing image_path or a_paths")

                # Per-clip viewport (defaults)
                vw = clip.viewport_w or 1080
                vh = clip.viewport_h or 1920
                oy = int(clip.offset_y or 0)

                seg_out = out_path.parent / f"seg_{i}.mp4"

                # Build video: scale to width, then crop vertical window at offset_y
                v = (
                    ffmpeg
                    .input(str(clip.image_path), loop=1, framerate=fps)
                    .filter("scale", vw, -1)                         # force scale to viewport width
                    .filter("crop", vw, vh, 0, oy)                   # crop x=0,y=offset
                    .filter("format", pix_fmt)
                )
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
                        quiet=not verbose,
                        capture_stderr=capture_stderr,
                        capture_stdout=capture_stdout
                    )

                )
                seg_files.append(seg_out)

            # concat
            concat_list = out_path.parent / "files.txt"
            concat_list.write_text(
                "\n".join(f"file '{p.name}'" for p in seg_files),
                encoding="utf-8"
            )

            with Timer(f"Rendering video → {out_path}", show_elapsed=show_progress):
                (
                    ffmpeg
                    .input(str(concat_list), format="concat", safe=0)
                    .output(str(out_path), c="copy")
                    .overwrite_output()
                    .run(
                        quiet=not verbose,
                        capture_stderr=capture_stderr,
                        capture_stdout=capture_stdout
                    )
                )

            return out_path

        except Exception:
            log_exception(f"Timeline.render({out_path})")
            raise
