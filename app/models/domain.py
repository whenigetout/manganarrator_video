from pydantic import BaseModel
from pathlib import Path
from typing import Literal, Any, Optional, List, Tuple

# atomic camera intent
class PanStep(BaseModel):
    dlg_id: int
    offset_y: int

# ONE renderable unit
class ClipSpec(BaseModel):
    image_path: Path
    audio_paths: list[Path]

    pan_steps: list[PanStep]

    viewport_w: int
    viewport_h: int

# a sequence of clips
class TimelineSpec(BaseModel):
    clips: list[ClipSpec]

# how ffmpeg should behave
class RenderConfig(BaseModel):
    fps: int = 24

    viewport_w: int = 1080
    viewport_h: int = 1920
    side_margin_px: int = 0
    first_dialog_margin_pct: float = 0.02
    safe_margin: int = 0

    vcodec: str = "h264_nvenc"
    preset: str = "p5"
    tune: str = "hq"
    cq: int = 23
    pix_fmt: str = "yuv420p"

    acodec: str = "aac"
    audio_bitrate: str = "192k"

    verbose: bool = True
    capture_stdout: bool = False
    capture_stderr: bool = False
    keep_segments: bool = False
