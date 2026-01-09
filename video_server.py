from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Tuple, Optional
from pydantic import BaseModel

from app.config import VideoConfig
from app.video_runner import VideoRunner
from app.chapter_video_builder import (
    ChapterVideoBuilder
)
from app.models.domain import OCRRun, OCRImageResult, RenderConfig
from app.models.api import DialoguePreviewOut, ImagePreviewOut


# -----------------------------------------------------------------------------
# App setup (same style as tts_server.py)
# -----------------------------------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = VideoConfig()
runner = VideoRunner(config)
builder = ChapterVideoBuilder(config)


# -----------------------------------------------------------------------------
# Preview endpoints
# -----------------------------------------------------------------------------

@app.get(
        "/video/runs/{run_id}/previews", 
        response_model=List[ImagePreviewOut]
    )
def get_run_previews(run_id: str):
    """
    Return preview data (pan offsets + crop boxes) for all images in a run.
    This does NOT run ffmpeg or build video.
    """

    run_dir = Path(str(config.output_root)) / run_id
    json_files = list(run_dir.rglob("ocr_output_with_bboxes.json"))

    if not json_files:
        raise HTTPException(status_code=404, detail="No OCR JSON found for run_id")

    results: List[ImagePreviewOut] = []

    for json_path in json_files:
        run = OCRRun.from_json_file(json_path)

        for img in run.images:
            image_path = (
                Path(str(config.input_root))
                / img.image_rel_path_from_root
                / img.image_file_name
            )

            settings = RenderConfig(
                viewport_w=builder.res_w,
                viewport_h=builder.res_h,
                safe_margin=builder.safe_margin,
                first_dialog_margin_pct=getattr(
                    config, "first_dialog_margin_pct", 0.02
                )
            )

            previews = builder.build_dialogue_previews(
                img,
                image_path=image_path,
                settings=settings
            )

            results.append(
                ImagePreviewOut(
                    image_id=img.image_id,
                    image_file_name=img.image_file_name,
                    image_rel_path_from_root=img.image_rel_path_from_root,
                    previews=previews,
                )
            )

    return results


# -----------------------------------------------------------------------------
# Build endpoints
# -----------------------------------------------------------------------------

@app.post("/video/runs/{run_id}/build")
def build_video_run(run_id: str):
    """
    Trigger actual video generation for a run.
    This WILL run ffmpeg and take time.
    """

    try:
        results = builder.build_run(run_id)
        return {
            "status": "ok",
            "videos_built": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
