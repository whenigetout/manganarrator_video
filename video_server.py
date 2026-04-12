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
import mn_contracts.pcc_backend as p
import mn_contracts.common as c
import threading
from jobs.jobs_db import (
    init_db,
    create_job,
    update_job,
    get_job,
)
from jobs.decorators import async_job
from contextlib import asynccontextmanager

# -----------------------------------------------------------------------------
# App setup (same style as tts_server.py)
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context Manager for application lifespan.
    Code before 'yield' runs on startup.
    Code after 'yield' runs on shutdown.
    """
    # print("Application startup: Initializing resources...")
    init_db()
    yield  # The application starts serving requests here
    # print("Application shutdown: Cleaning up resources...")
    # # Clean up resources
    # print("Resources cleaned up.")

app = FastAPI(lifespan=lifespan)

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

@app.post("/video/preview/ocrrun")
def build_video_preview_from_ocrrun(
    ocrrun: o.OCRRun = Body(...)
):
    """
    Build VideoPreview from an OCRRun and save it as JSON
    next to the OCR JSON file.

    This endpoint:
    - DOES NOT run ffmpeg
    - Only computes preview geometry + timing
    - Is safe to call frequently from frontend
    """

    try:
        # Use default render config (same as video pipeline)
        render_config = d.RenderConfig(
            viewport_w=builder.res_w,
            viewport_h=builder.res_h,
        )

        build_input = d.BuildVideoInput(
            ocr_run=ocrrun,
            render_config=render_config,
        )

        # Build preview (pure computation)
        video_preview = builder.build_video_preview(build_vid_input=build_input)

        # Resolve OCR JSON location
        ocr_json_path = Path(
            ocrrun.ocr_json_file.resolve(builder.config.media_root)
        )

        out_dir = ocr_json_path.parent / "video_preview"
        c.ensure_dir(out_dir)

        # Save next to OCR JSON
        preview_json_path = out_dir / "preview.json"

        c.save_model_json(
            video_preview,
            preview_json_path,
        )

        preview_json_ref = c.build_media_Ref(namespace=o.MediaNamespace.OUTPUTS, path=preview_json_path.relative_to(Path(builder.config.media_root)/o.MediaNamespace.OUTPUTS.value))

        return {
            "status": "ok",
            "video_preview_ref": preview_json_ref,
            "image_count": len(video_preview.image_previews),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Video preview build failed: {str(e)}",
        )

@app.post("/video/build/ocrrun", response_model=d.JobCreateResponse)
@async_job(d.JobType.build_ocrrun)
def build_video_from_ocrrun(
    ocrrun: o.OCRRun = Body(...),
    regen_existing_clips: bool = False,
    rebuild_preview: bool = False,
):
    """
    Build full final video from OCRRun.

    This endpoint:
    - Can rebuild preview if requested
    - Runs ffmpeg
    - Produces final concatenated video
    """

    try:
        render_config = d.RenderConfig(
            viewport_w=builder.res_w,
            viewport_h=builder.res_h,
        )

        build_input = d.BuildVideoInput(
            ocr_run=ocrrun,
            render_config=render_config,
        )

        return builder.build_video_from_ocrrun(
            build_vid_input=build_input,
            regen_existing_clips=regen_existing_clips,
            rebuild_preview=rebuild_preview,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Final video build failed: {str(e)}",
        )

@app.post("/video/build/from_preview", response_model=d.JobCreateResponse)
@async_job(d.JobType.build_from_preview)
def build_video_from_preview(
    video_preview: d.VideoPreview = Body(...),
    regen_existing_clips: bool = False,
):
    """
    Build full video from an already computed VideoPreview.
    Does NOT recompute preview geometry.
    """

    try:
        return builder.build_vid_from_video_prw(
            video_preview=video_preview,
            regen_existing_clips=regen_existing_clips,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Video build from preview failed: {str(e)}",
        )

@app.post("/video/build/image", response_model=d.JobCreateResponse)
@async_job(d.JobType.build_image)
def build_image_video(
    image_preview: d.ImagePreview = Body(...),
    regen_existing_clips: bool = False,
):
    """
    Build video for a single image (concatenate its segments).
    """

    try:
        render_config = d.RenderConfig(
            viewport_w=builder.res_w,
            viewport_h=builder.res_h,
        )

        return builder.build_img_video(
            img_prw=image_preview,
            render_config=render_config,
            regen_existing_clips=regen_existing_clips,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Image video build failed: {str(e)}",
        )

@app.post("/video/build/segment", response_model=d.JobCreateResponse)
@async_job(d.JobType.build_segment)
def build_segment_video(
    segment_preview: d.SegmentPreview = Body(...),
):
    """
    Build video for a single segment.
    """

    try:
        render_config = d.RenderConfig(
            viewport_w=builder.res_w,
            viewport_h=builder.res_h,
        )

        return builder.build_img_segment_video(
            seg_preview=segment_preview,
            render_config=render_config,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Segment video build failed: {str(e)}",
        )

@app.get("/video/status/{job_id}")
def get_video_status(job_id: str):
    job = get_job(job_id)

    if not job:
        return d.JobResponse(
            job_id=job_id,
            status=d.JobStatus.not_found
        )

    return job