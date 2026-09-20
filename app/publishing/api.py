"""Owner-authenticated publishing API, independent of legacy MangaNarrator routes."""
import hashlib
from html import escape
import hmac
import logging
import time
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, Body, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from .models import Profile, Provider, Review, RunInput, PublishingError
from .settings import Settings
from .store import Store, Conflict
from .oauth import OAuth
from .youtube import YouTube
from .workflow import Workflow, ACTIVE, media_path

PREFIX = "/video/publishing"


class SecretInput(BaseModel):
    config: dict


class ProviderInput(BaseModel):
    provider: Provider
    api_key: str = Field(default="", max_length=4096)


def public_profile(profile, settings):
    has_grant = bool(settings.get_secret("grant:" + profile.get("credential_id", "")))
    status = profile.get("connection_status", "connected") if has_grant else "disconnected"
    return {**{k: v for k, v in profile.items() if k != "credential_id"},
            "connected": status == "connected", "connection_status": status}


def public_run(run):
    result = {k: v for k, v in run.items() if k not in {"inputs", "approved_hash", "provider", "context", "transcript"}}
    result["profile"] = {k: v for k, v in run["profile"].items() if k != "credential_id"}
    return result


def session_token(key, now=None):
    value = str(int(now or time.time()) + 12 * 3600) + "." + secrets.token_hex(16)
    return value + "." + hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def valid_session(key, token):
    try:
        expires, nonce, signature = token.split(".")
        expected = hmac.new(key.encode(), f"{expires}.{nonce}".encode(), hashlib.sha256).hexdigest()
        return int(expires) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


class OAuthLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(arg.split("?", 1)[0] if isinstance(arg, str) and "/oauth/callback?" in arg else arg for arg in record.args)
        return True


def install_publishing(app, builder, settings=None):
    settings = settings or Settings()
    if settings.directory.is_relative_to(Path(builder.config.media_root).resolve()):
        raise ValueError("Publishing state must be outside the media root")
    store = Store(settings.directory / "publishing.db")
    oauth = OAuth(settings, store)
    workflow = Workflow(builder, settings, store, YouTube(oauth, settings))
    key = settings.owner_key()
    logging.getLogger("uvicorn.access").addFilter(OAuthLogFilter())
    router = APIRouter(prefix=PREFIX)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.startswith(PREFIX + "/"):
            return JSONResponse({"detail": "Invalid publishing request. Check required fields, lengths and supported values."}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    @app.middleware("http")
    async def protect(request, call_next):
        path = request.url.path
        if not path.startswith(PREFIX + "/"):
            return await call_next(request)
        origin = request.headers.get("origin")
        if request.headers.get("host") not in {urlsplit(item).netloc for item in settings.origins}:
            return JSONResponse({"detail": "Untrusted publishing host"}, status_code=403)
        if origin and origin not in settings.origins:
            return JSONResponse({"detail": "Untrusted publishing origin"}, status_code=403)
        if request.method == "OPTIONS":
            return Response(headers={"Access-Control-Allow-Origin": origin or "", "Access-Control-Allow-Credentials": "true",
                                     "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Publishing-Client, Idempotency-Key",
                                     "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS", "Vary": "Origin"})
        public = path in {PREFIX + "/info", PREFIX + "/oauth/callback"}
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
        authorized = bool(bearer) and hmac.compare_digest(bearer, key)
        authorized = authorized or valid_session(key, request.cookies.get("publishing_session"))
        if not public and not authorized:
            return JSONResponse({"detail": "Unlock publishing using Launch Studio.cmd"}, status_code=401)
        if not public and not path.endswith("/file") and request.headers.get("x-publishing-client") != "studio":
            return JSONResponse({"detail": "Missing publishing client header"}, status_code=403)
        try:
            response = await call_next(request)
        except Conflict as exc:
            response = JSONResponse({"detail": str(exc)}, status_code=409)
        except KeyError:
            response = JSONResponse({"detail": "Profile, provider or run not found"}, status_code=404)
        except (ValueError, ValidationError) as exc:
            # Pydantic reprs can contain supplied values. Never reflect secret inputs.
            detail = "Invalid settings. Check required fields and limits." if isinstance(exc, ValidationError) else str(exc)
            response = JSONResponse({"detail": detail}, status_code=422)
        except PublishingError as exc:
            response = JSONResponse({"detail": str(exc)}, status_code=422)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
        else:
            for header in ("Access-Control-Allow-Origin", "Access-Control-Allow-Credentials"):
                if header in response.headers:
                    del response.headers[header]
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @router.get("/info")
    def info():
        return {"enabled": True, "worker_running": bool(workflow.thread and workflow.thread.is_alive())}

    @router.post("/session")
    def session(response: Response):
        response.set_cookie("publishing_session", session_token(key), httponly=True, secure=settings.redirect_uri.startswith("https:"),
                            samesite="strict", path=PREFIX, max_age=12 * 3600)
        return {"ok": True}

    @router.get("/configuration")
    def configuration():
        return {"google_configured": bool(settings.get_secret("google_client")), "redirect_uri": settings.redirect_uri}

    @router.post("/configuration/google")
    def google(data: SecretInput):
        oauth.import_client(data.config)
        return {"ok": True}

    @router.get("/providers")
    def providers():
        return [{**item, "configured": bool(settings.get_secret("provider:" + item["id"]))} for item in store.objects("providers")]

    @router.post("/providers")
    def create_provider(data: ProviderInput):
        if not data.api_key:
            raise ValueError("API key is required")
        item = store.put("providers", data.provider.model_dump())
        settings.set_secret("provider:" + item["id"], data.api_key)
        return item

    @router.patch("/providers/{ident}")
    def edit_provider(ident: str, data: ProviderInput):
        store.get("providers", ident)
        item = store.put("providers", data.provider.model_dump(), ident)
        if data.api_key:
            settings.set_secret("provider:" + ident, data.api_key)
        return item

    @router.get("/profiles")
    def profiles():
        return [public_profile(item, settings) for item in store.objects("profiles")]

    @router.post("/profiles")
    def create_profile(data: Profile):
        if data.provider_id:
            store.get("providers", data.provider_id)
        return public_profile(store.put("profiles", data.model_dump()), settings)

    @router.patch("/profiles/{ident}")
    def edit_profile(ident: str, data: Profile):
        if data.provider_id:
            store.get("providers", data.provider_id)
        with oauth.lock:
            old = store.get("profiles", ident)
            return public_profile(store.put("profiles", {**old, **data.model_dump()}, ident), settings)

    @router.delete("/profiles/{ident}")
    def delete_profile(ident: str):
        with workflow.mutex, oauth.lock:
            if any(run["profile"]["id"] == ident and run["state"] not in {"completed", "canceled"} for run in store.runs()):
                raise Conflict("Cancel unfinished runs before deleting this profile")
            oauth.disconnect(store.get("profiles", ident))
            store.delete("profiles", ident)
        return {"ok": True}

    @router.post("/profiles/{ident}/connect")
    def connect(ident: str):
        return {"url": oauth.begin(ident)}

    @router.post("/profiles/{ident}/disconnect")
    def disconnect(ident: str):
        if any(run["profile"]["id"] == ident and run["state"] == "uploading" for run in store.runs()):
            raise Conflict("Wait for the active upload before disconnecting")
        oauth.disconnect(store.get("profiles", ident))
        return {"ok": True}

    @router.get("/oauth/callback")
    def callback(state: str, code: str = "", error: str = ""):
        if error or not code:
            data = store.consume_state(state)
            settings.delete_secret(data["verifier"])
            return HTMLResponse("<h1>Channel not connected</h1><p>Authorization was declined. Return to the studio and try again.</p>", status_code=400)
        try:
            oauth.finish(state, code)
        except (PublishingError, ValueError) as exc:
            return HTMLResponse(
                "<h1>Channel not connected</h1><p>" + escape(str(exc)) +
                "</p><p>Close this tab and start a new connection from Channel profiles. "
                "Do not refresh this callback page.</p>", status_code=422)
        return HTMLResponse("<h1>Channel connected</h1><p>You can close this tab and return to Audio Studio.</p>")

    @router.post("/runs")
    def create_run(data: RunInput, idempotency_key: str = Header(..., min_length=8, max_length=128)):
        with workflow.mutex:
            return public_run(workflow.create(data, idempotency_key))

    @router.get("/runs")
    def runs():
        return [public_run(run) for run in store.runs()[:100]]

    @router.get("/runs/{ident}")
    def run(ident: str):
        return public_run(store.run(ident))

    @router.patch("/runs/{ident}/metadata")
    def metadata(ident: str, data: Review):
        return public_run(workflow.review(ident, data))

    @router.post("/runs/{ident}/upload")
    def upload(ident: str, data: Review):
        run = store.run(ident)
        if run.get("approved_revision") == data.revision + 1 and run["state"] in {"uploading", "youtube_processing", "completed", "retry_wait"}:
            return public_run(run)
        return public_run(workflow.review(ident, data, upload=True))

    @router.post("/runs/{ident}/regenerate-metadata")
    def regenerate(ident: str):
        return public_run(workflow.regenerate(ident))

    @router.post("/runs/{ident}/retry")
    def retry(ident: str, confirm_restart: bool = Body(default=False, embed=True)):
        return public_run(workflow.retry(ident, confirm_restart))

    @router.post("/runs/{ident}/reopen-review")
    def reopen_review(ident: str):
        return public_run(workflow.reopen_review(ident))

    @router.post("/runs/{ident}/cancel")
    def cancel(ident: str):
        with workflow.mutex:
            result = store.change(ident, {"state": "canceled", "stage": "Canceled"},
                                  states={"awaiting_review", "failed", "needs_reauth", "needs_attention"})
            settings.delete_secret("upload:" + ident)
            return public_run(result)

    @router.get("/runs/{ident}/file")
    def file(ident: str, download: bool = False):
        artifact = store.run(ident).get("artifact")
        if not artifact:
            raise HTTPException(404, "Render is not ready")
        path = media_path(builder, artifact["ref"], output=True)
        return FileResponse(path, media_type="video/mp4", filename=path.name if download else None)

    app.include_router(router)
    return workflow
