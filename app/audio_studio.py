"""Portable studio routes. Existing MangaNarrator routes remain unchanged."""
import json
import subprocess
import threading
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from mn_contracts import common, ocr

from app.models import domain as d
from jobs.jobs_db import create_job, get_job, list_audio_jobs, update_job, update_progress


RENDER_LOCK = threading.Lock()
FRAME_LOCK = threading.Semaphore(2)


class FrameRequest(BaseModel):
    config: d.AudioVideoRequest
    seconds: float = Field(default=2, ge=0, le=7200)
    demo: bool = False


@lru_cache(maxsize=1)
def encoder_capabilities():
    try:
        result = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=640x360:d=0.1",
                                 "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=20)
        return {"nvenc": result.returncode == 0, "encoders": ["h264_nvenc", "libx264"] if result.returncode == 0 else ["libx264"]}
    except (OSError, subprocess.TimeoutExpired):
        return {"nvenc": False, "encoders": ["libx264"]}


def submit(builder, request):
    rc = request.render_config
    job_id = create_job(d.JobType.build_audio_video, metadata={
        "source_name": request.source_name or Path(request.audio_ref.path).name,
        "output_name": builder._safe_output_name(request.output_name),
        "kind": "preview" if request.preview_seconds else "video",
        "width": rc.viewport_w, "height": rc.viewport_h, "fps": rc.fps,
        "layouts": [v.kind for v in request.visualizers if v.enabled],
    })

    def run():
        with RENDER_LOCK:
            try:
                result = builder.build_audio_video(request, lambda value, stage: update_progress(job_id, value, stage))
                update_job(job_id, d.JobStatus.done, result={"type": d.JobType.build_audio_video.value, "data": result})
            except Exception as exc:
                update_progress(job_id, 0, "Failed")
                update_job(job_id, d.JobStatus.failed, error=str(exc))

    threading.Thread(target=run, daemon=True).start()
    return {"status": d.JobStatus.processing, "job_id": job_id}


def save_upload(builder, upload, category):
    folder = Path(builder.config.media_root) / "outputs" / "audio_video_uploads"
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix.lower()
    allowed = {"audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"},
               "video": {".mp4", ".mov", ".mkv", ".webm"}}[category]
    if suffix not in allowed:
        raise HTTPException(422, f"Unsupported {category} extension. Allowed: {', '.join(sorted(allowed))}")
    path = folder / (uuid.uuid4().hex + suffix)
    try:
        with path.open("wb") as target:
            total = 0
            while chunk := upload.file.read(1024 * 1024):
                total += len(chunk)
                if total > 512 * 1024 * 1024:
                    raise HTTPException(413, "Each upload must be under 512 MB")
                target.write(chunk)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0" if category == "audio" else "v:0",
                                "-show_entries", "stream=codec_type", "-of", "json", str(path)], capture_output=True, text=True, timeout=20)
        if probe.returncode or not json.loads(probe.stdout).get("streams"):
            raise HTTPException(422, f"File contains no readable {category} stream")
        return common.build_media_Ref(namespace=ocr.MediaNamespace.OUTPUTS, path=path, media_root=builder.config.media_root)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        upload.file.close()


def upload_audio(builder, audio_file, config_json):
    try:
        payload = json.loads(config_json) if config_json else {}
        if not isinstance(payload, dict):
            raise ValueError("Configuration must be a JSON object")
        # Validate settings before writing a potentially large audio upload.
        payload["audio_ref"] = {"namespace": "outputs", "path": "pending.wav"}
        request = d.AudioVideoRequest.model_validate(payload)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    request.source_name = Path(audio_file.filename or "Audio upload").name[:255]
    request.audio_ref = save_upload(builder, audio_file, "audio")
    # Each upload gets its own directory; repeated clicks cannot overwrite another job.
    request.run_id = f"{request.run_id or 'studio'}_{uuid.uuid4().hex[:8]}"
    return submit(builder, request)


def install_studio(app, builder):
    router = APIRouter(prefix="/video/audio")

    @router.get("/capabilities")
    def capabilities():
        return encoder_capabilities()

    @router.get("/jobs")
    def jobs():
        return list_audio_jobs()

    @router.post("/source")
    def source(audio_file: UploadFile = File(...)):
        from app.audio_frame import cached_audio
        name = Path(audio_file.filename or "Audio upload").name[:255]
        ref = save_upload(builder, audio_file, "audio")
        pcm, duration = cached_audio(builder, ref)
        return {"audio_ref": ref, "name": name, "duration": duration}

    @router.post("/frame")
    def frame(request: FrameRequest):
        from app.audio_frame import preview_png
        try:
            with FRAME_LOCK:
                png, timestamp = preview_png(builder, request.config, request.seconds, request.demo)
            return Response(png, media_type="image/png", headers={"Cache-Control": "no-store", "X-Frame-Time": str(timestamp)})
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/background")
    def background(video_file: UploadFile = File(...)):
        return save_upload(builder, video_file, "video")

    @router.get("/jobs/{job_id}/file")
    def download(job_id: str, download: bool = False):
        job = get_job(job_id)
        if not job or job.status != d.JobStatus.done or not job.result or job.result.type != d.JobType.build_audio_video:
            raise HTTPException(404, "No completed audio video for this job")
        ref = ocr.MediaRef.model_validate(job.result.data)
        path = Path(ref.resolve(Path(builder.config.media_root))).resolve()
        allowed = (Path(builder.config.media_root) / "outputs" / "audio_video").resolve()
        if not path.is_relative_to(allowed) or not path.is_file():
            raise HTTPException(404, "Video file not found")
        return FileResponse(path, media_type="video/mp4", filename=path.name if download else None)

    app.include_router(router)
    app.mount("/studio", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend" / "dist", html=True, check_dir=False), name="audio-studio")
