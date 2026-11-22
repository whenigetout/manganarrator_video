"""Run the story project API independently of the desktop rendering service."""

import os
from secrets import compare_digest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import install_story_routes
from .store import StoryStore


def create_app():
    root = os.environ.get("STORY_STUDIO_ROOT")
    if not root or not Path(root).is_absolute():
        raise RuntimeError("Set STORY_STUDIO_ROOT to an absolute private data directory")

    app = FastAPI(title="Story Studio Preparation API")
    token = os.environ.get("STORY_SHARED_TOKEN")
    if token:
        expected = f"Bearer {token}".encode()

        @app.middleware("http")
        async def authenticate(request: Request, call_next):
            presented = request.headers.get("authorization", "").encode()
            if not compare_digest(presented, expected):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

    install_story_routes(app, StoryStore(root))
    return app
