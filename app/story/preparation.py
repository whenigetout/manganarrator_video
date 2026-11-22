"""Run the story project API independently of the desktop rendering service."""

import os
from pathlib import Path

from fastapi import FastAPI

from .api import install_story_routes
from .store import StoryStore


def create_app():
    root = os.environ.get("STORY_STUDIO_ROOT")
    if not root or not Path(root).is_absolute():
        raise RuntimeError("Set STORY_STUDIO_ROOT to an absolute private data directory")

    app = FastAPI(title="Story Studio Preparation API")
    install_story_routes(app, StoryStore(root))
    return app
