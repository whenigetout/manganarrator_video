"""Story routes are additive; no OCR, model loading, or automatic publishing."""
import os
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from mn_contracts.story import StoryProject
from .importer import import_story
from .store import StoryStore, Conflict, safe_id
from .timeline import compile_timeline


class ImportRequest(BaseModel):
    format: str = "json"
    content: str = Field(max_length=10_000_000)


class RevisionRequest(BaseModel):
    revision: int = Field(ge=0)


class RestoreRequest(RevisionRequest):
    restore_revision: int = Field(ge=0)


class RenderRequest(RevisionRequest):
    chapter_id: str
    scene_id: str | None = None
    width: int = Field(default=1280, ge=128, le=1920)
    height: int = Field(default=720, ge=128, le=1920)
    fps: int = Field(default=24, ge=1, le=60)

    @model_validator(mode="after")
    def valid_size(self):
        if self.width % 2 or self.height % 2:
            raise ValueError("Output dimensions must be even")
        return self


def install_story(app, builder):
    root = os.environ.get("STORY_STUDIO_ROOT") or str(Path(builder.config.media_root) / "outputs" / "story_studio")
    return install_story_routes(app, StoryStore(root), production=True)


def install_story_routes(app, store, *, production=False):
    router = APIRouter(prefix="/video/story")

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "Project, revision or asset not found") from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/schema")
    def schema():
        return StoryProject.model_json_schema()

    @router.get("/projects")
    def projects():
        return call(store.list)

    @router.post("/import")
    def import_project(request: ImportRequest):
        project = call(import_story, request.content, request.format)
        return call(store.create, project)

    @router.get("/projects/{project_id}")
    def project(project_id: str):
        return call(store.read, project_id)

    @router.delete("/projects/{project_id}")
    def delete_project(project_id: str, revision: int):
        call(store.delete, project_id, revision)
        return {"deleted": True}

    @router.put("/projects/{project_id}")
    def save(project_id: str, project: StoryProject):
        return call(store.save, project_id, project, project.revision, allow_new_scenes=not production)

    @router.get("/projects/{project_id}/history")
    def history(project_id: str):
        return call(store.history, project_id)

    @router.post("/projects/{project_id}/restore")
    def restore(project_id: str, request: RestoreRequest):
        return call(store.restore, project_id, request.restore_revision, request.revision)

    @router.post("/projects/{project_id}/duplicate")
    def duplicate(project_id: str, request: RevisionRequest):
        return call(store.duplicate, project_id, request.revision)

    @router.post("/projects/{project_id}/assets")
    def upload(project_id: str, file: UploadFile = File(...), kind: str = Form(...),
               revision: int = Form(...), segment_id: str | None = Form(default=None)):
        try:
            if not production and kind != "image":
                raise HTTPException(422, "Only image uploads are supported in preparation mode")
            result, asset = call(store.upload, project_id, file, kind, revision, segment_id)
            return {"project": result, "asset": asset}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, "Media could not be decoded; check the file and FFmpeg installation") from exc
        finally:
            file.file.close()

    @router.get("/projects/{project_id}/assets/{asset_id}")
    def asset(project_id: str, asset_id: str):
        project = call(store.read, project_id)
        asset = next((a for a in project.assets if a.id == asset_id), None)
        if not asset:
            raise HTTPException(404, "Asset not found")
        path = call(store.asset_path, project, asset)
        return FileResponse(path, media_type="audio/wav" if asset.kind == "audio" else "image/png")

    @router.get("/projects/{project_id}/timeline")
    def timeline(project_id: str, chapter_id: str | None = None, scene_id: str | None = None):
        return call(compile_timeline, call(store.read, project_id), chapter_id, scene_id)

    if production:
        install_render_routes(router, store, call)
    app.include_router(router)
    return store


def install_render_routes(router, store, call):
    import threading

    from app.audio_studio import RENDER_LOCK
    from app.models.domain import JobType, JobStatus
    from jobs.jobs_db import create_job, get_job, update_job, update_progress, list_story_jobs
    from .render import render_story

    @router.get("/projects/{project_id}/renders")
    def renders(project_id: str):
        call(store.read, project_id)
        return list_story_jobs(project_id)

    @router.post("/projects/{project_id}/render")
    def render(project_id: str, request: RenderRequest):
        project = call(store.read, project_id)  # immutable snapshot for this job
        if project.revision != request.revision:
            raise HTTPException(409, "Reload before rendering the newest revision")
        timeline = call(compile_timeline, project, request.chapter_id, request.scene_id)
        if not timeline["ready"]:
            raise HTTPException(422, timeline["conflicts"])
        job_id = create_job(JobType.build_story_video, metadata={"project_id": project.id, "title": project.title,
                           "revision": project.revision, "chapter_id": request.chapter_id, "scene_id": request.scene_id})
        def run():
            try:
                with RENDER_LOCK:
                    render_story(store, project, store.folder(project_id) / "renders" / job_id,
                        request.chapter_id, request.scene_id, request.width, request.height, request.fps,
                        lambda value, stage: update_progress(job_id, value, stage))
                update_job(job_id, JobStatus.done, result={"type": JobType.build_story_video.value,
                    "data": {"project_id": project.id, "revision": project.revision}})
            except Exception as exc:
                update_job(job_id, JobStatus.failed, error=str(exc))
        threading.Thread(target=run, daemon=True).start()
        return {"job_id": job_id, "status": "processing"}

    @router.get("/projects/{project_id}/renders/{job_id}/{filename}")
    def rendered(project_id: str, job_id: str, filename: str, download: bool = False):
        call(store.read, project_id)
        call(safe_id, job_id)
        job = get_job(job_id)
        if filename not in {"episode.mp4", "manifest.json"} or not job or job.status != JobStatus.done or not job.result:
            raise HTTPException(404, "Completed render not found")
        if job.result.type != JobType.build_story_video or job.result.data.get("project_id") != project_id:
            raise HTTPException(404, "Render does not belong to this project")
        path = call(store.folder, project_id) / "renders" / job_id / filename
        return FileResponse(path, filename=filename if download else None,
                            media_type="video/mp4" if filename.endswith("mp4") else "application/json")
