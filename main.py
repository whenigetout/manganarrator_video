
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

json_path = Path(
    "E:/pcc_shared/manga_narrator_runs/outputs/"
    "api_batch_20260107_162347_8b0e1197/"
    "test/ocr_output_with_corrected_bboxes.json"
)

# 1. Load raw JSON
with json_path.open("r", encoding="utf-8") as f:
    raw = json.load(f)

# 2. Validate + parse into OCRRun
ocrrun: o.OCRRun = o.OCRRun.model_validate(raw)

print("✅ OCRRun loaded successfully")

b = builder(VideoConfig())

out_path = Path("output/test/ocrrun_test/ocrrun.mp4")

b.build_ocrrun_video(
    ocrrun=ocrrun,
    out_path=out_path,
    settings=d.RenderConfig()
)
