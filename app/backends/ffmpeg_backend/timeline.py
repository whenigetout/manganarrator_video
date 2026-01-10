from clip import FClip
from typing import List, Optional, Callable
from concat import concat_clips

class Timeline:
    """
    Orchestrates multiple FClips in sequence.
    No domain meaning. No IO.
    """

    def __init__(self, clips: Optional[List[FClip]] = None):
        self.clips: List[FClip] = clips or []

    def add(self, clip: FClip) -> "Timeline":
        self.clips.append(clip)
        return self

    def extend(self, clips: List[FClip]) -> "Timeline":
        self.clips.extend(clips)
        return self

    # ----------------------------
    # Global transforms
    # ----------------------------

    def apply(self, fn: Callable[[FClip], FClip]) -> "Timeline":
        """
        Apply a transformation to every clip.
        """
        self.clips = [fn(c) for c in self.clips]
        return self

    def fade_in_all(self, duration: float) -> "Timeline":
        return self.apply(lambda c: c.fade_in(duration))

    def fade_out_all(self, duration: float) -> "Timeline":
        return self.apply(
            lambda c: c.fade_out(duration, start=0)
        )

    # ----------------------------
    # Between-clip effects
    # ----------------------------

    def fade_between(self, duration: float) -> "Timeline":
        """
        Applies fade-out to clip i and fade-in to clip i+1
        """
        for i in range(len(self.clips) - 1):
            self.clips[i].fade_out(duration, start=0)
            self.clips[i + 1].fade_in(duration)
        return self

    # ----------------------------
    # Build
    # ----------------------------

    def build(self) -> FClip:
        if not self.clips:
            raise RuntimeError("Cannot build empty timeline.")
        return concat_clips(self.clips)
