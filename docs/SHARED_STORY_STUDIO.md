# Shared Story Studio

GitHub `main` contains the UI, API and Sites adapter. The Windows build and the private Site use the same React Story Studio. Both send edits to one preparation API, whose private disk is the source of truth for projects, assets and revisions. Git pulls update code. Opening a project retrieves its current data from that API.

## Canonical preparation API

On an always-on host with persistent private storage, install `requirements-preparation.txt` and run `python scripts/sync_contracts.py`. Configure:

| Setting | Value |
| --- | --- |
| `STORY_STUDIO_ROOT` | Absolute path on a persistent volume outside the checkout. |
| `STORY_SHARED_TOKEN` | The same long random secret on the host, desktop, and Site. |

Run `python -m uvicorn app.story.preparation:create_app --factory --host 127.0.0.1 --port 8085 --workers 1` behind an HTTPS reverse proxy. Keep one writer process. Verify that an unauthenticated request to `/video/story/projects` returns HTTP 401 before using the HTTPS endpoint. A loopback development instance may omit the token.

Back up the whole project root with writes stopped. Restore into an empty directory and point the only writer at it. To migrate legacy local projects, copy the entire local root into a fresh canonical root with writes stopped, before creating projects on the shared host.

## Windows desktop

Set `STORY_SHARED_URL` to the preparation API's HTTPS origin and `STORY_SHARED_TOKEN` to the shared secret in the server process environment. Run the usual Windows launcher and open `/studio/#story`. The separate **Local Story Rendering** tab opens local projects and production routes. Installing `requirements-story.txt` provides the `httpx` dependency for the shared connection.

An existing private environment file can hold these names. If using Uvicorn directly with a dotenv file, install `python-dotenv` and pass `--env-file <private-file>`. The batch launcher uses inherited environment variables. Keep secrets in local ignored files or host settings. A Git pull on a new computer needs the server address and its credential once. Each project then opens from the canonical API automatically.

## ChatGPT Sites

Use an owner-private Site build. From `frontend/`, run `npm ci`, set `VITE_STORY_SITE=1` for `npm run build`, then run `node sites/package.mjs`. This emits the Worker at repo-root `dist/server/index.js` with the existing Vite assets embedded. The Sites deployment workflow also needs the target Site ID in a Worker-mode `.openai/hosting.json` manifest. Use GitHub `main` as the input for each Site build.

Configure server-side Site values:

| Setting | Value |
| --- | --- |
| `STORY_SHARED_URL` | The same preparation API HTTPS origin used on Windows. |
| `STORY_SHARED_TOKEN` | The same preparation API secret. |
| `STORY_OWNER_EMAIL` | Exact email associated with the owner's signed-in ChatGPT account. |

The Worker enforces the owner email and forwards project requests with the server-side credential. Sites and Windows browsers never receive the token. Validate owner sign-in and anonymous rejection in production before opening a real manuscript. With the preparation host and Site running, the tablet can use the Site while Windows is off.

## Editing and rendering

Create a project by pasting text, or import a structured manuscript. Add chapters and scenes, edit narration and visual prompts, and upload ChatGPT-generated images in Visuals. Shared authoring autosaves after a pause. Wait for **Saved** before switching away. On a stale revision, the server keeps the newer project and the editor retains the unsaved draft and offers a manuscript download. Reopen the project and reapply the edits you want to keep. Adding scenes preserves imported ones. Historical restores that would remove scenes are rejected. Manuscript JSON is portable and omits uploaded media bindings.

The shared editor is for preparation. It does not call desktop FFmpeg. A pinned project-and-assets handoff from shared storage to the local renderer remains future work.
