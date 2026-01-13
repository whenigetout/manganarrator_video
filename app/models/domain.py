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
    first_dialog_top_padding: int = 10
    last_dialog_bottom_padding: int = 10

    vcodec: str = "h264_nvenc"
    preset: str = "p5"
    tune: str = "hq"
    cq: int = 23
    pix_fmt: str = "yuv420p"

    acodec: str = "aac"
    audio_bitrate: str = "192k"
    default_silent_clip_duration: float = 3

    verbose: bool = True
    capture_stdout: bool = False
    capture_stderr: bool = False
    keep_segments: bool = False

class Size(BaseModel):
    w: int
    h: int

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
    # SegmentRenderSpan describes the FINAL, ffmpeg-safe render intent.
    #
    # All coordinates are expressed in a padded, scaled-image space:
    # - image_scale: uniform scale applied to the original image
    # - empty_space_top / bottom: black space to be added before cropping
    # - crop_y1 / crop_y2: crop box AFTER padding is applied
    #
    # This guarantees that preview rendering and ffmpeg rendering
    # produce identical visuals.

    crop_y1: int
    crop_y2: int
    render_height: int
    image_scale: float
    empty_space_top: int
    empty_space_bottom: int

class Segment(BaseModel):
    segment_id: int
    base_y1: int
    base_y2: int
    image_info: o.ImageInfo
    video_dialogue_ids: List[int] = Field(default_factory=list)

class RenderedSegment(BaseModel):
    segment: Segment
    render_span: SegmentRenderSpan
    viewport_size: Size

class SegmentPreview(BaseModel):
    rendered_segment: RenderedSegment
    duration: float
    video_dialogue_lines: List[VideoDialogueLine] = Field(default_factory=list)

class ImagePreview(BaseModel):
    run_id: str
    image_id: int
    base_timeline: List[SegmentPreview]

class VideoPreview(BaseModel):
    run_id: str
    image_previews: List[ImagePreview]

class BuildVideoInput(BaseModel):
    ocr_run: o.OCRRun
    render_config: RenderConfig

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
