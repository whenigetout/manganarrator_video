"""Recoverable single-host orchestration using the existing audio renderer."""
import hashlib
import json
import logging
import random
import threading
import time
from pathlib import Path
from filelock import FileLock
from app.models.domain import AudioVideoRequest
from app.audio_studio import render_locked, encoder_capabilities
from .models import Metadata, PublishingError
from .store import Conflict
from .metadata import generate

log = logging.getLogger(__name__)
ACTIVE = {"queued", "rendering", "generating_metadata", "uploading", "youtube_processing", "retry_wait"}
EDITABLE = {"awaiting_review"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_identity(path):
    with Path(path).open("rb") as source:
        hasher = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
        checksum = hasher.hexdigest()
    return {"size": Path(path).stat().st_size, "sha256": checksum}


def media_path(builder, ref, output=False):
    from mn_contracts.ocr import MediaRef
    root = Path(builder.config.media_root).resolve()
    path = Path(MediaRef.model_validate(ref).resolve(root)).resolve()
    allowed = root / "outputs" / ("audio_video" if output else "audio_video_uploads")
    if not path.is_relative_to(allowed) or not path.is_file():
        raise ValueError("Media must be an existing studio upload or generated publishing video")
    return path


class Workflow:
    def __init__(self, builder, settings, store, youtube):
        self.builder, self.settings, self.store, self.youtube = builder, settings, store, youtube
        self.stopping = threading.Event()
        self.mutex = threading.RLock()
        self.thread = None
        self.worker_lock = FileLock(str(settings.directory / "worker.lock"))

    def start(self):
        self.worker_lock.acquire(timeout=0)
        for run in self.store.runs():
            if run["state"] == "rendering":
                self.store.change(run["id"], {"state": "queued", "stage": "Recovering interrupted render", "progress": 0})
        self.thread = threading.Thread(target=self.loop, name="publishing-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join()
        self.worker_lock.release()

    def create(self, request, key):
        profile = self.store.get("profiles", request.profile_id)
        if not profile.get("channel_id") or not profile.get("credential_id"):
            raise ValueError("Connect this channel profile before preparing a video")
        if not self.settings.get_secret("grant:" + profile["credential_id"]):
            raise ValueError("Channel disconnected. Reconnect this profile first.")
        config = dict(request.config if request.config is not None else profile["preset"])
        for field in ("run_id", "preview_seconds"):
            config.pop(field, None)
        config.update(audio_ref=request.audio_ref, source_name=request.source_name)
        render = AudioVideoRequest.model_validate(config)
        if render.render_config.vcodec == "h264_nvenc" and not encoder_capabilities()["nvenc"]:
            render.render_config.vcodec = "libx264"
        inputs = [{"ref": render.audio_ref.model_dump(mode="json")}]
        inputs += [{"ref": ref.model_dump(mode="json")} for ref in render.background.media_refs]
        for item in inputs:
            item["identity"] = file_identity(media_path(self.builder, item["ref"]))
        provider = self.store.get("providers", profile["provider_id"]) if profile["provider_id"] else None
        return self.store.create_run({"profile": profile, "provider": provider, "request": render.model_dump(mode="json"),
                                      "inputs": inputs, "context": request.context, "transcript": request.transcript,
                                      "source_name": request.source_name}, key, digest(request.model_dump(mode="json")))

    def review(self, ident, review, upload=False):
        with self.mutex:
            run = self.store.run(ident)
            if not run.get("artifact"):
                raise Conflict("Render must finish before review")
            path = media_path(self.builder, run["artifact"]["ref"], output=True)
            if file_identity(path) != run["artifact"]["identity"]:
                raise Conflict("Rendered video changed on disk. Prepare a new video before approving.")
            revision = run["revision"] + 1
            values = review.model_dump(exclude={"metadata", "revision"})
            changes = {"metadata": review.metadata.model_dump(), "review": values, "revision": revision,
                       "metadata_error": None, "error": None, "attempts": 0, "next_retry": 0}
            if upload:
                changes.update(state="uploading", stage="Upload queued", progress=0,
                               approved_revision=revision, approved_hash=digest([run["artifact"], run["profile"]["channel_id"], changes["metadata"], values]))
            return self.store.change(ident, changes, states=EDITABLE, revision=review.revision)

    def regenerate(self, ident):
        with self.mutex:
            run = self.store.run(ident)
            current = self.store.get("profiles", run["profile"]["id"])
            provider = self.store.get("providers", current["provider_id"]) if current["provider_id"] else None
            profile = {**run["profile"], **{key: current[key] for key in ("provider_id", "prompt", "tags", "language")}}
            return self.store.change(ident, {"state": "generating_metadata", "stage": "Generating metadata", "revision": run["revision"] + 1,
                                            "approved_revision": None, "metadata_error": None, "provider": provider, "profile": profile}, states=EDITABLE)

    def retry(self, ident, restart=False):
        with self.mutex:
            run = self.store.run(ident)
            if run["state"] not in {"failed", "needs_reauth", "needs_attention", "retry_wait"}:
                raise Conflict("This run is not waiting for a retry")
            if run["state"] == "needs_attention" and not run.get("video_id") and not restart:
                raise Conflict("Check YouTube Studio first, then explicitly confirm restarting this upload")
            if restart:
                if run.get("video_id"):
                    raise Conflict("This run already has a YouTube video ID; a second upload is blocked")
                self.settings.delete_secret("upload:" + ident)
            phase = "youtube_processing" if run.get("video_id") else run.get("resume_state", "queued")
            return self.store.change(ident, {"state": phase, "stage": "Retry queued", "error": None, "attempts": 0, "next_retry": 0,
                                            "session_created": False if restart else run.get("session_created", False)})

    def reopen_review(self, ident):
        with self.mutex:
            run = self.store.run(ident)
            if not run.get("artifact") or run.get("video_id") or run.get("session_created") or self.settings.get_secret("upload:" + ident):
                raise Conflict("Only a rendered video without an initiated YouTube upload can return to review")
            return self.store.change(ident, {"state": "awaiting_review", "stage": "Ready for review", "error": None,
                                            "revision": run["revision"] + 1, "approved_revision": None, "approved_hash": None},
                                     states={"failed", "needs_reauth"})

    def loop(self):
        while not self.stopping.is_set():
            try:
                for run in reversed(self.store.runs()):
                    if self.stopping.is_set():
                        break
                    if run["state"] in ACTIVE and run.get("next_retry", 0) <= time.time():
                        self.step(run["id"])
            except Exception as exc:
                log.warning("Publishing queue temporarily unavailable: %s", type(exc).__name__)
                self.stopping.wait(5)
            self.stopping.wait(1)

    def step(self, ident):
        run = self.store.run(ident)
        phase = run.get("resume_state") if run["state"] == "retry_wait" else run["state"]
        if phase not in ACTIVE:
            return
        if run.get("video_id") and phase != "youtube_processing":
            self.store.change(ident, {"state": "youtube_processing", "stage": "YouTube processing", "next_retry": 0})
            return
        self.store.change(ident, {"state": phase, "error": None, "next_retry": 0})
        try:
            if phase in {"queued", "rendering"}:
                if not run["artifact"]:
                    for item in run["inputs"]:
                        if file_identity(media_path(self.builder, item["ref"])) != item["identity"]:
                            raise PublishingError("Source audio or background changed. Prepare a new video.")
                    self.store.change(ident, {"state": "rendering", "stage": "Rendering", "progress": 0})
                    request = AudioVideoRequest.model_validate({**run["request"], "run_id": "publish_" + ident})
                    def progress(value, stage):
                        if self.stopping.is_set():
                            raise InterruptedError()
                        self.store.change(ident, {"progress": value, "stage": stage})
                    ref = render_locked(self.builder, request, progress)
                    artifact = {"ref": ref.model_dump(mode="json"), "identity": file_identity(media_path(self.builder, ref.model_dump(mode="json"), True))}
                    self.store.change(ident, {"artifact": artifact})
                self.store.change(ident, {"state": "generating_metadata", "stage": "Generating metadata", "progress": 0, "attempts": 0})
            elif phase == "generating_metadata":
                warning = None
                try:
                    if not run["provider"]:
                        raise PublishingError("No metadata provider selected. Enter metadata or set a provider for future videos.")
                    key = self.settings.get_secret("provider:" + run["provider"]["id"])
                    if not key:
                        raise PublishingError("Metadata API key missing. Update the provider or enter metadata manually.")
                    metadata = generate(run["provider"], key, run["profile"], {"filename": run["source_name"], "context": run["context"],
                                        "transcript": run["transcript"], "language": run["profile"]["language"]})
                except PublishingError as exc:
                    warning = str(exc)
                    metadata = run.get("metadata") or Metadata(title=Path(run["source_name"]).stem.replace("<", "").replace(">", "")[:100] or "My recording",
                                                               tags=run["profile"]["tags"]).model_dump()
                defaults = {key: run["profile"][key] for key in ("privacy", "category", "made_for_kids", "contains_synthetic_media")}
                self.store.change(ident, {"state": "awaiting_review", "stage": "Ready for review", "progress": 100,
                                        "metadata": metadata, "metadata_error": warning, "review": run.get("review") or defaults})
            elif phase == "uploading":
                approved = digest([run["artifact"], run["profile"]["channel_id"], run["metadata"], run["review"]])
                if run.get("approved_revision") != run["revision"] or approved != run.get("approved_hash"):
                    raise PublishingError("Approval no longer matches this video. Prepare and review a new run.", "needs_attention")
                path = media_path(self.builder, run["artifact"]["ref"], True)
                if file_identity(path) != run["artifact"]["identity"]:
                    raise PublishingError("Rendered file changed after approval. Upload blocked.", "needs_attention")
                self.store.change(ident, {"stage": "Uploading to " + run["profile"]["channel_name"]})
                result = self.youtube.upload(run, path, lambda changes: self.store.change(ident, changes), self.stopping.is_set)
                self.store.change(ident, {"state": "youtube_processing", "stage": "YouTube processing", "progress": 100, "attempts": 0,
                                        "upload_bytes": path.stat().st_size, "upload_total": path.stat().st_size,
                                        "video_id": result["id"], "video_url": "https://www.youtube.com/watch?v=" + result["id"],
                                        "actual_privacy": result.get("status", {}).get("privacyStatus"), "processing_started": time.time()})
                try:
                    self.settings.delete_secret("upload:" + ident)
                except Exception:
                    log.warning("Upload completed; deferred credential-store cleanup for run %s", ident)
            elif phase == "youtube_processing":
                done, privacy = self.youtube.processing(run)
                if not done and time.time() - run.get("processing_started", time.time()) > 48 * 3600:
                    raise PublishingError("YouTube processing is taking over 48 hours. Check YouTube Studio.", "needs_attention")
                self.store.change(ident, {"state": "completed" if done else "youtube_processing", "stage": "Ready on YouTube" if done else "YouTube processing",
                                        "actual_privacy": privacy, "next_retry": 0 if done else time.time() + 30, "attempts": 0})
        except InterruptedError:
            return
        except Exception as exc:
            if isinstance(exc, PublishingError):
                state, message, delay = exc.kind, str(exc), exc.delay
            else:
                state, message, delay = "failed", f"{phase.replace('_', ' ').capitalize()} failed ({type(exc).__name__}). Check source files and configuration, then retry.", 0
                log.warning("Publishing run %s failed in %s: %s", ident, phase, type(exc).__name__)
            attempts = run.get("attempts", 0) + 1
            if state == "retry_wait" and attempts >= 8:
                state, message = "failed", message + " Automatic retry limit reached. Retry manually when the issue is resolved."
            self.store.change(ident, {"state": state, "stage": state.replace("_", " ").capitalize(), "error": message,
                                    "resume_state": phase, "attempts": attempts,
                                    "next_retry": time.time() + max(delay, min(300, 2 ** attempts) + random.random()) if state == "retry_wait" else 0})
