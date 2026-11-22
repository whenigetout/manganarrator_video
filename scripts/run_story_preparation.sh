#!/usr/bin/env sh
# Run from a Linux or Android PRoot installation with a built preparation UI.
set -eu
cd "$(dirname "$0")/.."
export STORY_STUDIO_ROOT="${STORY_STUDIO_ROOT:-${HOME}/story-studio-projects}"
exec .venv/bin/python -m uvicorn app.story.preparation:create_editor_app --factory \
    --host 127.0.0.1 --port 8085 --workers 1
