FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
RUN npm run build:preparation

FROM python:3.12-slim
WORKDIR /studio
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-preparation.txt ./
COPY scripts/sync_contracts.py ./scripts/
RUN python -m pip install --no-cache-dir -r requirements-preparation.txt \
    && python scripts/sync_contracts.py
COPY app ./app
COPY --from=frontend /build/frontend/dist ./frontend/dist
ENV STORY_STUDIO_ROOT=/data
CMD ["sh", "-c", "exec python -m uvicorn app.story.preparation:create_hosted_app --factory --host 0.0.0.0 --port \"${PORT:-8085}\" --workers 1"]
