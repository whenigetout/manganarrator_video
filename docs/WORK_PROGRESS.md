# Story Narration Studio work progress

## Objective

Use this GitHub repo for both tablet authoring and Windows production. Both editors must read and write one private project, with revision checks and durable assets. Windows continues to run the production pipeline.

## Milestone 1 · Audit complete

| Area | Existing implementation |
| --- | --- |
| Manga | `video_server.py` exposes OCR preview/save/load, OCR run and preview builds, image/segment/chapter video, and job status. `app/chapter_video_builder.py` and `app/backends/ffmpeg_backend/` assemble timed clips and media. OCR/TTS inputs use shared `mn_contracts`. |
| Studio | Windows Conda launchers serve FastAPI with a React/Vite build at `/studio/`; `#story` selects the story editor. `app/audio_studio.py` handles the separate audio visualizer. |
| Story | `app/story/importer.py` accepts structured Markdown or manuscript JSON. `StoryStudio.jsx` edits production lines, prompts and shots, supports uploads and revision history, and exports manuscript JSON and render manifests. Imported scene structure is fixed and draft saves are manual. |
| Media | `store.py` normalizes images with Pillow and imported speech with FFmpeg/FFprobe. `timeline.py` compiles measured speech, stills and sound beds. `render.py` renders previews and MP4 chapters using FFmpeg. Review timed text/subtitle export separately before promising it for story chapters. |
| Persistence | `STORY_STUDIO_ROOT` holds JSON, immutable revision snapshots and assets. Writes use a process lock, revision checks and atomic replacement of current JSON. SQLite job state is separate. This store requires one writer process. |
| Publishing | Optional `app/publishing/` handles Google OAuth, channel profiles, metadata, approval and YouTube upload. Story render does not invoke publishing. |
| Tests | Backend unittest suite covers story/API, media and mocked publishing. Playwright covers Story Studio, Audio Studio and publishing frontend workflows. Prior results are in `PROJECT_CONTEXT.md`. |

## ChatGPT Sites verification

- **Publish from existing code:** Sites supports compatible local projects. Its deployment accepts a static bundle or Cloudflare Worker ES module. The Vite frontend can produce static assets. The FastAPI/FFmpeg process does not fit this runtime.
- **GitHub updates and write-back:** The documented workflow saves and deploys builds through Sites. Its native source credential belongs to the Site source repository. No documented native GitHub auto-deploy or bidirectional mapping to this project's GitHub repo was found. A connected GitHub app can access authorized data independently of source deployment.
- **Persistence:** Sites provides D1 for records and R2 for files. Both devices can use one deployed app's storage through authenticated endpoints. Local files and local preview databases do not sync with hosted bindings. OpenAI documents no built-in combined database and file backup/restore.
- **Python and external APIs:** Worker code can call external HTTP services. FastAPI would need a separate reachable host. Browser clients would also need appropriate origin and auth handling. An address on the Windows desktop is unavailable when that desktop is off.
- Sources: [Sites creation workflow](https://learn.chatgpt.com/docs/sites/creating-a-site), [Data and connections](https://learn.chatgpt.com/docs/sites/data-and-connections), [OpenAI Sites help](https://help.openai.com/en/articles/20001339-creating-and-using-chatgpt-sites), and the available Sites deployment, storage and identity capability references. No Site was registered or deployed for the audit.

## Architecture decision

Use the same React application and Python story models and routes from this repo. Run one preparation API on a privately reachable, always-on host with one worker and a persistent disk outside the checkout. The owner-private Site Worker and the Windows loopback server proxy the same preparation API. Each serves a build of the same React source. Keep JSON and revision checks. Keep personal stories and media outside GitHub. A separate SQLite database or GitHub-backed document store would add schema/hosting or asset and conflict-handling work without replacing a missing requirement.

For Windows rendering, plan an authenticated handoff of a pinned project revision and its referenced files to a temporary render input. The render input is derived, read-only project data. Write any production changes to the canonical API with the existing revision guard. Verify this path separately before claiming shared Windows production. Keep local launchers and existing local projects working throughout.

For backup, stop writes and copy the entire private project root, including history and assets, to a second private location. Restore to an empty private directory and point the server at that directory. Do not run independent writers on a copied root, synced folder, or live network mount. Select and validate host and private access before deployment.

## Optional AI

Start with ChatGPT copy/paste using selected excerpts. Ask for critique, narration, scene breakdown or image prompts, and review drafts before saving. A future authenticated MCP tool could expose scoped preparation actions when the user's ChatGPT access supports it. The OpenAI API is a separate metered option, with no keys or paid calls added in this phase. See [API pricing](https://platform.openai.com/pricing/).

## Milestone 2 · Preparation API complete

Run this locally with one worker. Set the root to an absolute private path outside the checkout. On Windows PowerShell, set it with `$env:STORY_STUDIO_ROOT = 'C:\Private\StoryStudio'`.

```bash
python -m pip install -r requirements-preparation.txt
python scripts/sync_contracts.py
export STORY_STUDIO_ROOT=/absolute/private/story-studio
python -m uvicorn app.story.preparation:create_app --factory --host 127.0.0.1 --port 8085 --workers 1
```

Open `http://127.0.0.1:8085/docs` to exercise the API with the synthetic `fixtures/story-demo.md`. The API reuses project import/list/read/save, history/restore, image uploads and timeline checks. Stale edits return HTTP 409. The existing desktop entry point retains audio uploads, rendering and job routes. Set `STORY_SHARED_TOKEN` before any remote use and serve it through HTTPS. See [shared setup](SHARED_STORY_STUDIO.md).

## Files changed and tests

- Milestone 1: `docs/WORK_PROGRESS.md`, `AGENTS.md`. Source baseline `5fa1614`.
- Milestone 2: `app/story/api.py`, `app/story/preparation.py`, `requirements-preparation.txt`, `tests/test_story_preparation.py`, and this checkpoint.
- Linux baseline: 57 backend tests and the Vite production build passed after installing Story/publishing dependencies and contracts. A first test attempt before the install completed failed on missing imports.
- Linux after changes: 59 backend tests passed, including real CPU FFmpeg export, mocked publishing, and simulated tablet/desktop edits, stale-save rejection, image retrieval and restart. Full desktop API import, isolated preparation import without render modules, loopback Uvicorn HTTP smoke test and `git diff --check` passed.
- Physical tablet, browser UI, Windows launchers, NVENC, full multi-service manga inference and live YouTube OAuth/upload were not exercised.

## Milestone 3 · Shared editor and Sites build

- Same React Story Studio in the Site Worker and local desktop app. Shared mode supports paste, project/chapter/scene naming, adding chapters and scenes, revision-aware autosave, image planning and manuscript export. The original local renderer is available separately.
- Changed `frontend/src/{main.jsx,StoryStudio.jsx}`, `frontend/vite.config.js`, `frontend/sites/`, `app/story/{api,preparation,shared,store}.py`, `video_server.py`, and `tests/test_story_preparation.py`. Configuration and backups are in `docs/SHARED_STORY_STUDIO.md`.
- Linux verification: all 60 backend tests passed. Both Vite modes built successfully and the Sites Worker packaged.
- Local HTTP integration exercised the packaged Worker with simulated Sites identity and the real desktop server against one authenticated preparation API. It passed creation, reads, desktop chapter edits, adding a scene, stale revision rejection and anonymous/cross-origin denial. Chromium launch was blocked by the container's Unix socket restriction, so browser interaction is pending.

## Milestone 4 · Hosted and Android-compatible preparation entry points

- Added a standalone Vite build and FastAPI static mount, HTTP Basic browser authentication plus bearer API authentication, an authenticated Docker deployment with mandatory persistent mount, and a loopback launcher for Android through Termux and Debian PRoot.
- Changed `app/story/preparation.py`, `frontend/src/main.jsx`, `frontend/package.json`, `Dockerfile`, `.dockerignore`, `scripts/run_story_preparation.sh`, `tests/test_story_preparation.py`, and the setup docs.
- Railway Free has limited compute credit and a 0.5 GB persistent volume. No authenticated Railway workspace was available. The Android fallback has instructions for PC access to the tablet's existing store over USB port forwarding.
- Linux verification: standalone preparation build, live loopback HTTP smoke test, and 61 backend tests passed. No Docker daemon, Android device, or authenticated provider workspace was available for live verification.

## Known problems and next exact task

Use [Run Story Studio](RUN_STORY_STUDIO.md) to deploy in the owner's Railway workspace or install on their Android tablet. Verify a synthetic project from both devices and after restart before migrating real stories. Follow with the pinned revision-and-assets handoff for desktop rendering.

## Resume in a new ChatGPT Work session

Check out GitHub `main`. Read this file, `AGENTS.md` and `SHARED_STORY_STUDIO.md`, then inspect the relevant recent commit. Keep existing environment files private and reuse them when available. Record setting names and host/deployment state here without copying secrets. Update this file after each tested milestone.

## Library navigation and project removal

- Story Studio opens in the library. Opening a project or importing a manuscript enters its editor. Returning to Library saves pending edits first and closes the project.
- Delete uses a revision check and a recoverable marker. Normal read, write and listing routes treat the deleted project as unavailable. See `RUN_STORY_STUDIO.md` for recovery.
- Added the Story Studio favicon to regular, preparation, Docker and Sites builds.
- Verified 62 backend tests, regular and preparation Vite builds, Sites packaging, and import/readback plus timeline compilation for all episodes of the user's privately delivered manuscript. The manuscript is held outside this repository.
