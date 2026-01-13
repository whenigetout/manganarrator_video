from pydantic import BaseModel, Field
from pathlib import Path
from typing import Literal, Any, Optional, List, Tuple
from mn_contracts import ocr as o
import app.models.exceptions as ex

# how ffmpeg should behave
class RenderConfig(BaseModel):
    fps: int = 24

    viewport_w: int = 1080
    viewport_h: int = 1920
    side_margin_px: int = 0
    first_dialog_margin_pct: float = 0.02
    first_dialog_top_padding: int = 10
    last_dialog_bottom_padding: int = 10
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

class Size(BaseModel):
    w: int
    h: int

class Frame(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

class DialogueLine_preview(o.DialogueLine):
    preview_frame: Frame
    audio_ref: o.MediaRef
    duration: float

class OCRImg_preview(o.OCRImage):
    frame_size: Size
    side_margin_px: int = 0
    frame_padding_top: int = 10
    img_scale: float
    dialogue_lines: List[DialogueLine_preview]

class OCRRun_preview(o.OCRRun):
    images: List[OCRImg_preview]

# These are for building video from an ocrrun
class VideoDialogueLine(BaseModel):
    id: int
    image_id: str
    text: str
    speaker: str
    emotion: str
    original_bbox: o.OriginalImageBBox
    audio_ref: o.MediaRef


class SegmentRenderSpan(BaseModel):
    render_y1: int
    render_y2: int
    render_height: int
    scale: float

class Segment(BaseModel):
    segment_id: int
    base_y1: int
    base_y2: int
    image_info: o.ImageInfo
    dialogue_ids: List[int] = Field(default_factory=list)

class RenderedSegment(BaseModel):
    segment: Segment
    render_span: SegmentRenderSpan
    viewport_size: Size

class DialogueAudio(BaseModel):
    run_id: str
    image_id: int
    image_ref: o.MediaRef
    dialogue_id: int
    audio_ref: o.MediaRef

class SegmentPreview(BaseModel):
    rendered_segment: RenderedSegment
    duration: float
    dialogues: List[DialogueAudio] = Field(default_factory=list)

class ImageSegmentPreview(BaseModel):
    run_id: str
    image_id: int
    base_timeline: List[SegmentPreview]

class BuildSegmentPreviewInput(BaseModel):
    ocr_run: o.OCRRun
    render_config: RenderConfig

class BuildVideoInput(BaseModel):
    ocr_run: o.OCRRun
    render_config: RenderConfig
    base_timeline: List[ImageSegmentPreview]

def to_video_dialogue(dlg: o.DialogueLine, audio_ref: o.MediaRef) -> VideoDialogueLine:
    if dlg.original_bbox is None:
        raise ex.BuildVideoError(
            f"Dialogue {dlg.id} has no bbox; cannot render video"
        )

    return VideoDialogueLine(
        id=dlg.id,
        image_id=dlg.image_id,
        text=dlg.text,
        speaker=dlg.speaker,
        emotion=dlg.emotion,
        original_bbox=dlg.original_bbox,
        audio_ref=audio_ref,
    )
