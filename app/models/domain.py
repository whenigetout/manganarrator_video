from pydantic import BaseModel, Field
from pathlib import Path
from typing import Literal, Any, Optional, List, Union
from mn_contracts import ocr as o
import app.models.exceptions as ex
from enum import Enum

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
    audio_default_sample_rate: int = 44100
    default_silent_clip_duration: float = 3

    verbose: bool = True
    capture_stdout: bool = False
    capture_stderr: bool = False
    keep_segments: bool = False

class AudioVideoBackgroundConfig(BaseModel):
    mode: Literal["generated", "media"] = "generated"
    media_refs: List[o.MediaRef] = Field(default_factory=list)
    generated_style: Literal["aurora", "nebula", "gradient", "plasma"] = "aurora"
    color_a: str = "#111827"
    color_b: str = "#ec4899"
    color_c: str = "#22d3ee"
    blur: int = 28
    playback_rate: float = 1.0

class AudioVisualizerConfig(BaseModel):
    enabled: bool = True
    kind: Literal["circular", "horizontal", "vertical"] = "circular"
    position: Literal["center", "top_left", "top_right", "bottom_left", "bottom_right", "top", "bottom", "left", "right"] = "bottom_right"
    width: int = 420
    height: int = 420
    margin_x: int = 96
    margin_y: int = 96
    opacity: float = 0.95
    colors: str = "0x22d3ee|0xec4899|0xfacc15|0xa78bfa"
    mode: Literal["bar", "line", "dot"] = "bar"
    scale: Literal["lin", "sqrt", "cbrt", "log"] = "sqrt"
    frequency_bins: int = 96
    gain: float = 1.0
    background_opacity: float = 0.0

class AudioVideoRequest(BaseModel):
    audio_ref: o.MediaRef
    run_id: Optional[str] = None
    output_name: str = "audio_visualizer_video.mp4"
    render_config: RenderConfig = Field(default_factory=lambda: RenderConfig(viewport_w=2560, viewport_h=1440, fps=30))
    background: AudioVideoBackgroundConfig = Field(default_factory=AudioVideoBackgroundConfig)
    visualizers: List[AudioVisualizerConfig] = Field(default_factory=lambda: [AudioVisualizerConfig(), AudioVisualizerConfig(kind="horizontal", position="bottom", width=1800, height=220, margin_y=72, frequency_bins=128)])

class Size(BaseModel):
    w: int
    h: int

# These are for building video from an ocrrun
class VideoDialogueLine(BaseModel):
    id: int
    image_id: int
    text: str
    speaker: str
    emotion: str
    original_bbox: o.OriginalImageBBox
    audio_ref: o.MediaRef

class AudioLayer(BaseModel):
    id: str
    label: str
    media_ref: o.MediaRef
    start_at: float = 0.0
    volume: float = 1.0
    loop: bool = False
    enabled: bool = True
    trim_start_sec: float = 0.0
    trim_end_sec: Optional[float] = None
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0

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
    empty_space_left: int
    empty_space_right: int

class Segment(BaseModel):
    segment_id: int
    image_id: int
    run_id: str
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
    include_in_output: bool = True
    audio_layers: List[AudioLayer] = Field(default_factory=list)
    out_dir_ref: o.MediaRef
    out_file_ref: o.MediaRef

class ImagePreview(BaseModel):
    run_id: str
    image_id: int
    base_timeline: List[SegmentPreview]
    include_in_output: bool = True
    audio_layers: List[AudioLayer] = Field(default_factory=list)
    out_dir_ref: o.MediaRef
    out_file_ref: o.MediaRef

class VideoPreview(BaseModel):
    run_id: str
    image_previews: List[ImagePreview]
    render_config: RenderConfig
    audio_layers: List[AudioLayer] = Field(default_factory=list)
    out_dir_ref: o.MediaRef
    out_file_ref: o.MediaRef

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

# for background jobs
class JobStatus(str, Enum):
    processing = "processing"
    done = "done"
    failed = "failed"
    not_found = "not_found"

class JobType(str, Enum):
    build_ocrrun = "build_ocrrun"
    build_image = "build_image"
    build_segment = "build_segment"
    build_from_preview = "build_from_preview"
    build_audio_video = "build_audio_video"

class JobResult(BaseModel):
    type: JobType
    data: Union[o.MediaRef, dict]

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: Optional[JobResult] = None
    error: Optional[str] = None

class JobCreateResponse(BaseModel):
    status: JobStatus  # always "processing"
    job_id: str
