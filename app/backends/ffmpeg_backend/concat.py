from clip import FClip
from typing import Iterable, List
import ffmpeg

def concat_clips(clips: Iterable[FClip]) -> FClip:
    """
    Concatenate multiple FClips sequentially.

    Rules:
    - All clips must have compatible formats
    - Video-only, audio-only, or AV all supported
    - Returns a NEW FClip (does not mutate inputs)
    """

    clips = list(clips)
    if not clips:
        raise ValueError("Cannot concat empty clip list.")

    has_video = any(c.v is not None for c in clips)
    has_audio = any(c.a is not None for c in clips)

    v_streams: List = []
    a_streams: List = []

    for c in clips:
        if has_video:
            if c.v is None:
                raise RuntimeError("All clips must have video if any clip has video.")
            v_streams.append(c.v)

        if has_audio:
            if c.a is None:
                raise RuntimeError("All clips must have audio if any clip has audio.")
            a_streams.append(c.a)

    # Build concat filter inputs
    inputs = []
    inputs.extend(v_streams)
    inputs.extend(a_streams)

    out = ffmpeg.concat(
        *inputs,
        v=1 if has_video else 0,
        a=1 if has_audio else 0,
        n=len(clips),
    )

    if has_video and has_audio:
        v, a = out
    elif has_video:
        v = out
        a = None
    else:
        v = None
        a = out

    return FClip(v=v, a=a, fps=clips[0].fps)