# app/backends/ffmpeg_backend/concat.py

from typing import Iterable
import ffmpeg

from app.backends.ffmpeg_backend.clip import FClip


def concat_clips(clips: Iterable[FClip]) -> FClip:
    clips = list(clips)
    if not clips:
        raise ValueError("Cannot concat empty clip list.")

    # --- strict validation ---
    for i, clip in enumerate(clips):
        if clip.v is None or clip.a is None:
            raise RuntimeError(
                f"Clip {i} must have BOTH video and audio for concat"
            )

    fps = next((c.fps for c in clips if c.v is not None), clips[0].fps)

    video_inputs = []
    audio_inputs = []

    for clip in clips:
        assert clip.v is not None
        assert clip.a is not None

        # reset timestamps to avoid drift
        v = clip.v.filter("setpts", "PTS-STARTPTS")
        a = clip.a.filter("asetpts", "PTS-STARTPTS")

        video_inputs.append(v)
        audio_inputs.append(a)

    # --- concat video ---
    v_out = ffmpeg.concat(
        *video_inputs,
        v=1,
        a=0,
        n=len(video_inputs),
    )

    # --- concat audio ---
    a_out = ffmpeg.concat(
        *audio_inputs,
        v=0,
        a=1,
        n=len(audio_inputs),
    )

    return FClip(v=v_out, a=a_out, fps=fps)
