from pydantic import BaseModel, Field, model_validator
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
    scale: Literal["lin", "sqrt", "cbrt", "log"] = "log"
    frequency_bins: int = Field(default=64, ge=8, le=256)
    gain: float = Field(default=1.0, ge=0.1, le=10)
    radius: float = Field(default=0.27, ge=0.05, le=0.4)
    bar_width: float = Field(default=0.55, ge=0.1, le=0.95)
    glow: float = Field(default=0.6, ge=0, le=2)
    smoothing: float = Field(default=0.72, ge=0, le=0.98)
    min_frequency: float = Field(default=40, ge=20, le=1000)
    max_frequency: float = Field(default=16000, ge=1001, le=20000)
    background_opacity: float = 0.0

class AudioVideoRequest(BaseModel):
    audio_ref: o.MediaRef
    source_name: Optional[str] = Field(default=None, max_length=255)
    run_id: Optional[str] = None
    output_name: str = "audio_visualizer_video.mp4"
    render_config: RenderConfig = Field(default_factory=lambda: RenderConfig(viewport_w=2560, viewport_h=1440, fps=30, preset="p1"))
    background: AudioVideoBackgroundConfig = Field(default_factory=AudioVideoBackgroundConfig)
    visualizers: List[AudioVisualizerConfig] = Field(default_factory=lambda: [AudioVisualizerConfig(position="center", width=850, height=850)])
    preview_seconds: Optional[float] = Field(default=None, ge=1, le=15)

    @model_validator(mode="after")
    def validate_audio_video(self):
        import re
        rc = self.render_config
        if not (128 <= rc.viewport_w <= 3840 and 128 <= rc.viewport_h <= 3840):
            raise ValueError("Resolution must be between 128 and 3840 pixels")
        if rc.viewport_w % 2 or rc.viewport_h % 2 or not 1 <= rc.fps <= 60:
            raise ValueError("Resolution must be even; FPS must be 1-60")
        if rc.vcodec not in ("h264_nvenc", "libx264"):
            raise ValueError("Audio video encoder must be h264_nvenc or libx264")
        if self.run_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.run_id):
            raise ValueError("run_id may contain only letters, digits, underscores and hyphens")
        if len(self.visualizers) > 4:
            raise ValueError("At most four visualizers are supported")
        for viz in self.visualizers:
            if not 32 <= viz.width <= 3840 or not 32 <= viz.height <= 3840:
                raise ValueError("Visualizer size must be 32-3840 pixels")
            if not 0 <= viz.opacity <= 1 or not 0 <= viz.background_opacity <= 1:
                raise ValueError("Opacity must be between zero and one")
            if viz.margin_x < 0 or viz.margin_y < 0:
                raise ValueError("Margins must be nonnegative")
            if not all(re.fullmatch(r"(?:#|0x)?[0-9a-fA-F]{6}", color) for color in viz.colors.split("|")):
                raise ValueError("Colors must be six-digit hex values separated by |")
        if self.background.mode == "media" and not self.background.media_refs:
            raise ValueError("Choose at least one background video")
        if not 0.05 <= self.background.playback_rate <= 8:
            raise ValueError("Background playback rate must be 0.05-8")
        for color in (self.background.color_a, self.background.color_b, self.background.color_c):
            if not re.fullmatch(r"(?:#|0x)?[0-9a-fA-F]{6}", color):
                raise ValueError("Background colors must be six-digit hex values")
        return self

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
    progress: float = 0
    stage: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

class JobCreateResponse(BaseModel):
    status: JobStatus  # always "processing"
    job_id: str
