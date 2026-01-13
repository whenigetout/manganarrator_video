from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Tuple, Optional
from pydantic import BaseModel
import app.models.domain as d
from app.config import VideoConfig
from app.chapter_video_builder import (
    ChapterVideoBuilder
)
import mn_contracts.ocr as o

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
builder = ChapterVideoBuilder(config)


# -----------------------------------------------------------------------------
# Preview endpoints
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Build endpoints
# -----------------------------------------------------------------------------

@app.post("/video/build/ocrrun")
def build_video_from_ocrrun(
    ocrrun: o.OCRRun = Body(...)
):
    """
    Build narrated manga video directly from an OCRRun object.
    This WILL run ffmpeg and may take time.
    """

    try:
        # Render settings (match preview + video pipeline)
        settings = d.RenderConfig(
            viewport_w=builder.res_w,
            viewport_h=builder.res_h,
            safe_margin=builder.safe_margin,
            first_dialog_margin_pct=getattr(
                config, "first_dialog_margin_pct", 0.02
            ),
        )

        video_ref = builder.build_ocrrun_video(
            ocrrun=ocrrun,
            settings=settings,
        )

        return {
            "status": "ok",
            "output_video_ref": video_ref,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Video build failed: {str(e)}",
        )
