"""Serve the story editor and project API without desktop rendering dependencies."""

from base64 import b64encode
import os
from pathlib import Path
from secrets import compare_digest
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import install_story_routes
from .store import StoryStore


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(*, serve_frontend=False, require_auth=False):
    root = os.environ.get("STORY_STUDIO_ROOT")
    if not root or not Path(root).is_absolute():
        raise RuntimeError("Set STORY_STUDIO_ROOT to an absolute private data directory")

    browser_password = os.environ.get("STORY_BROWSER_PASSWORD")
    token = os.environ.get("STORY_SHARED_TOKEN")
    if require_auth and not browser_password:
        raise RuntimeError("Set STORY_BROWSER_PASSWORD before starting the hosted editor")

    app = FastAPI(title="Story Studio Preparation")
    if token or browser_password:
        expected_bearer = f"Bearer {token}".encode() if token else None
        expected_basic = b"Basic " + b64encode(f"story:{browser_password}".encode()) if browser_password else None

        @app.middleware("http")
        async def authenticate(request: Request, call_next):
            presented = request.headers.get("authorization", "").encode()
            bearer = expected_bearer is not None and compare_digest(presented, expected_bearer)
            browser = expected_basic is not None and compare_digest(presented, expected_basic)
            if not (bearer or browser):
                headers = {"Cache-Control": "no-store"}
                if expected_basic:
                    headers["WWW-Authenticate"] = 'Basic realm="Private Story Studio", charset="UTF-8"'
                return JSONResponse({"detail": "Authentication required"}, status_code=401, headers=headers)
            if browser and request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if (request.headers.get("sec-fetch-site") in ("cross-site", "same-site")
                        or (origin and urlsplit(origin).netloc != request.headers.get("host"))):
                    return JSONResponse({"detail": "Cross-origin story writes are forbidden"}, status_code=403)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

    install_story_routes(app, StoryStore(root))
    if serve_frontend:
        if not (FRONTEND_DIST / "index.html").is_file():
            raise RuntimeError("Build the frontend with npm run build:preparation first")
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="story-studio")
    return app


def create_editor_app():
    return create_app(serve_frontend=True)


def create_hosted_app():
    root = os.environ.get("STORY_STUDIO_ROOT")
    volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if volume and root != volume:
        raise RuntimeError("Set STORY_STUDIO_ROOT to the Railway volume mount path")
    # Linux mountinfo also detects bind mounts on the same filesystem.
    mountinfo = Path("/proc/self/mountinfo")
    mounts = {line.split()[4] for line in mountinfo.read_text().splitlines()} if mountinfo.is_file() else set()
    if not root or root not in mounts:
        raise RuntimeError("Mount a persistent volume at STORY_STUDIO_ROOT before starting")
    return create_app(serve_frontend=True, require_auth=True)
