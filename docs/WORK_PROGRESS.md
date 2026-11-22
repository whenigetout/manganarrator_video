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

Use the same React application and Python story models and routes from this repo. Run one preparation API on a privately reachable, always-on host with one worker and a persistent disk outside the checkout. Both devices eventually open the same URL. Keep JSON and revision checks. Keep personal stories and media outside GitHub. A separate SQLite database or GitHub-backed document store would add schema/hosting or asset and conflict-handling work without replacing a missing requirement.

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

Open `http://127.0.0.1:8085/docs` to exercise the API with the synthetic `fixtures/story-demo.md`. The API reuses project import/list/read/save, history/restore, image uploads and timeline checks. Stale edits return HTTP 409. The existing desktop entry point retains audio uploads, rendering and job routes. This local API has no authentication. Before any remote use, provide private authenticated access and verify the boundary.

## Files changed and tests

- Milestone 1: `docs/WORK_PROGRESS.md`, `AGENTS.md`. Source baseline `5fa1614`.
- Milestone 2: `app/story/api.py`, `app/story/preparation.py`, `requirements-preparation.txt`, `tests/test_story_preparation.py`, and this checkpoint.
- Linux baseline: 57 backend tests and the Vite production build passed after installing Story/publishing dependencies and contracts. A first test attempt before the install completed failed on missing imports.
- Linux after changes: 59 backend tests passed, including real CPU FFmpeg export, mocked publishing, and simulated tablet/desktop edits, stale-save rejection, image retrieval and restart. Full desktop API import, isolated preparation import without render modules, loopback Uvicorn HTTP smoke test and `git diff --check` passed.
- Physical tablet, browser UI, Windows launchers, NVENC, full multi-service manga inference and live YouTube OAuth/upload were not exercised.

## Known problems and next exact task

No shared host or cross-device frontend is configured. Next, add preparation mode to the existing Vite/React Studio and serve it from the preparation API under the same origin. Reuse Library, Manuscript and Visuals. Add plain-text project creation and revision-aware autosave first. On a conflict, retain unsaved edits and prompt for recovery. Test with two browser contexts and a tablet viewport before selecting the private deployment and integrating the Windows render handoff.

## Resume in a new ChatGPT Work session

Check out `story-studio-shared` in this repository. Read this file and `AGENTS.md`, then `git status -sb` and `git log -4 --oneline`. Read only the relevant diff and tests for the next exact task. Update this file and commit each tested milestone on this branch. Public deployment, paid services, deletion of existing data, and merge to main require approval.
