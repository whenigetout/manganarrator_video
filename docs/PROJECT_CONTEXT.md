# manganarrator_video: project context

Source review: 2026-10-21. Baseline commit: `508facb4e3ad5b1488f406a49fb1d5737c63903a`.
For later sessions, compare relevant paths against that commit; avoid re-auditing unrelated services.

## Purpose and boundaries

FastAPI video rendering plus the embedded React/Vite Audio Studio and additive Story Studio. Primary owner of story production UI, measured timelines and MP4 export.

Reuse existing FClip/FFmpeg helpers and the audio render lock. Keep manga /video/build/* and Audio Studio routes compatible. Publishing remains opt-in (PUBLISHING_ENABLED); no automatic YouTube upload. Story assets live outside tracked source.

## Code map

video_server.py; app/audio_studio.py; app/audio_spectrum.py; app/audio_frame.py; app/chapter_video_builder.py; app/backends/ffmpeg_backend/; app/publishing/; frontend/src/; jobs/jobs_db.py; scripts/launch_studio.py

## Setup and checks

See README.md and docs/STORY_STUDIO.md for dependency and launch commands. API: `python -m uvicorn video_server:app --host 127.0.0.1 --port 8084` (one worker). Frontend: `cd frontend`, `npm ci`, `npm run build`; development `npm run dev` proxies /video to 8084. Backend suite: `python -m unittest discover -s tests -v`. Browser suite: `npm run test:e2e` with a running API and installed browser.

## Known details and gaps

FFmpeg and FFprobe must be on PATH. config.yaml sets media_root. Audio Studio is served at /studio/. Backend tests include real media encoding as well as mocked publishing. GPU/NVENC and live publishing require separate validation; do not infer them from CPU/mocked tests.

## Current state / next work

This note was grounded in source inspection at the baseline above. Runtime verification for this service is recorded below only when actually executed. Documentation-only edits do not establish that GPU inference, external APIs, or the complete distributed manga pipeline work in this environment.

For story production, first inspect [Story Studio in the video service](https://github.com/whenigetout/manganarrator_video/blob/main/docs/STORY_STUDIO.md). The first slice uses imported segment audio; OCR and Paddle are unchanged. Native story TTS is a later adapter, not an image-shaped workaround.

## Related repositories

[Central ecosystem map](https://github.com/whenigetout/manganarrator/blob/main/docs/ECOSYSTEM.md) owns service responsibilities and the cross-repo task routing table. Consult it only for work crossing a service boundary.

### Story Studio increment — 2026-10-21

- Added `app/story/{api,importer,store,timeline,render}.py`, `frontend/src/StoryStudio.jsx` and `story.css`, plus `fixtures/story-demo.md` and `tests/test_story.py`.
- Entry: `/studio/#story`; API `/video/story`. Shared model: `mn_contracts.story.StoryProject` (Python package 0.1.18 / TS package 0.1.12). Upgrade contracts when pulling this increment.
- Reuses `FClip`, `concat_files`, `audio_studio.RENDER_LOCK`, SQLite jobs and the existing status endpoint. New `build_story_video` jobs retain their source revision. Does not alter manga DTOs or publishing behavior.
- Source/draft separation, locks, saved history and optimistic revisions protect edits. Speech imports normalize/measure actual audio and fingerprint text/voice/direction. Manual visual placements survive reflow; conflicts block export.
- New `requirements-story.txt` is the portable studio subset. Private data uses `STORY_STUDIO_ROOT` or media_root/outputs/story_studio. See [user/API guide](STORY_STUDIO.md) for schema grammar and launch details.
- Executed: all 53 backend tests passed, including 12 Story Studio tests and a real CPU MP4 render; Vite production build passed; shared TypeScript build passed. Playwright passed the real Story Studio import/edit/take/image/timeline/preview/download/reload/lock flow; desktop and 390 px mobile screenshots were visually checked, with no page errors or horizontal overflow. Both existing Audio Studio editor browser tests also passed, including a real preview and reload, after setting a valid Linux media root for the test server.
- Not exercised: GPU/NVENC, local Chatterbox inference, Windows launchers, real OAuth/upload, complete multi-service manga inference. Existing publishing tests use mocks.
- Next priorities: native story-segment TTS adapter; portable project/media bundle import/export; scene structure editing; automated adaptation drafts with actual diff/lock semantics. Current profile selectors save editorial instructions only. Do not advertise them as an AI rewrite engine.
