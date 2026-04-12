
from pathlib import Path
from app.backends.ffmpeg_backend.clip import FClip
from app.backends.ffmpeg_backend.concat import concat_clips

img = "input/images/a_returners_magic_should_be_special_6_1.jpg"
out = "output/test"
audio1 = "input/audio/voice1.wav"
audio2 = "input/audio/voice2.wav"

from pathlib import Path
import json
from mn_contracts import ocr as o
from app.chapter_video_builder import ChapterVideoBuilder as builder
from app.config import VideoConfig
import app.models.domain as d

ocr_json_path = Path(
    "E:/pcc_shared/manga_narrator_runs/outputs/api_batch_20260111_180315_777be1a4/A_Returners_Magic_Should_Be_Special_1/ocrrun_final.json"
)

preview_json_path = Path(
    "E:/pcc_shared/manga_narrator_runs/outputs/api_batch_20260111_180315_777be1a4/A_Returners_Magic_Should_Be_Special_1/video_preview/preview.json"
)

# 1. Load raw JSON
with ocr_json_path.open("r", encoding="utf-8") as f:
    raw_ocr = json.load(f)

# with preview_json_path.open("r", encoding="utf-8") as f:
#     raw_ocr = json.load(f)

# 2. Validate + parse into OCRRun
# video_preview: d.VideoPreview = d.VideoPreview.model_validate(raw)
ocrrun: o.OCRRun = o.OCRRun.model_validate(raw_ocr)

print("✅ OCRRun loaded successfully")

b = builder(VideoConfig())
b.build_video_from_ocrrun(
    build_vid_input=d.BuildVideoInput(
        ocr_run=ocrrun,
        render_config=d.RenderConfig()
    )
)

# b.build_vid_from_video_prw(
#     video_preview=video_preview,
#     regen_existing_clips=True
# )

# img_prw = next(prw for prw in video_preview.image_previews if prw.image_id == 2)
# seg_prw = next((prw for prw in img_prw.base_timeline if prw.rendered_segment.segment.segment_id==1))

# b.build_img_segment_video(
#     seg_preview=seg_prw,
#     render_config=d.RenderConfig()
# )

