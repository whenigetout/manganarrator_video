# Audio Studio And YouTube Publishing

## Scope

This is an optional, single-owner, single-host extension of the existing MangaNarrator video backend. It reuses the exact audio renderer, MediaRef contracts, FFT spectrum analysis and FFmpeg/NVENC output path. Existing OCR/image/segment/chapter endpoints and the render-only studio remain available. There is no automatic upload on render completion: the durable pipeline stops at review.

Normal flow: **audio -> saved channel/preset -> render -> metadata -> review -> resumable upload -> YouTube processing**.

The frontend is React + Vite, not Next.js. The launcher serves its production build from FastAPI, avoiding a second development server for everyday use.

## Launching

Double-click `Launch Studio.cmd`. The wrapper applies PowerShell execution-policy bypass to that invocation only; it does not change your machine's policy. The launcher prefers `STUDIO_PYTHON`, then the standard Miniconda/Anaconda `manganarrator-video` environment, then the active Conda prefix. It checks the base backend, FFmpeg, FFprobe and Node/npm; installs missing optional dependencies; runs `npm ci` when the lockfile changes; and builds the React app when source/build inputs are newer.

Prerequisites for a new machine:

1. Follow the original repository setup, including `mn_contracts`, `config.yaml`, and a valid `media_root`.
2. Install `requirements.txt` and `requirements-audio.txt` in the existing Conda environment.
3. Install FFmpeg/FFprobe on PATH and Node.js compatible with Vite 7 (20.19+ or 22.12+).
4. Run the launcher. Its first launch needs internet access for missing packages.

The default URL is `http://127.0.0.1:8084/studio/`. If that port belongs to another service, the launcher uses a free nearby port without stopping the other service. It remembers its port and reuses a matching, authenticated studio on subsequent launches. If the chosen port changes, update Google's registered redirect URI to the exact value shown under Google OAuth setup.

Keep the launcher window open; Ctrl+C gracefully stops the server. After interruption, rerun it and revisit Publishing jobs. Do not run multiple publishing backend workers or reload-mode servers against the same publishing state: an OS file lock enforces one publishing worker.

For a custom Python installation, set `STUDIO_PYTHON` to the environment's `python.exe`. `STUDIO_PORT` changes the preferred local port. `scripts/launch_studio.ps1 -NoBrowser` starts without opening a browser. Running the launcher normally unlocks the studio using a fragment that is removed from the address bar and exchanged for an HttpOnly browser session.

## Google Cloud: One-Time Setup

1. Create/select a Google Cloud project and enable **YouTube Data API v3**.
2. Configure the OAuth consent screen. While the app is in Testing, add your Google account(s) as test users.
3. Create an OAuth client of type **Web application**. Add the exact Authorized redirect URI shown in the studio, typically `http://127.0.0.1:8084/video/publishing/oauth/callback`.
4. Download the client JSON. In **Channel profiles and setup -> Google OAuth setup**, import that JSON. Do not put it in this Git repository.
5. Create a profile, save it, then press **Connect YouTube**. Select the account and actual YouTube channel you intend to use, including the appropriate Brand Account channel when Google offers it.
6. Grant both upload and read access. The backend queries the authorized channel and saves its channel ID/name. Confirm these match your intention.

Scopes are `youtube.upload` and `youtube.readonly`. Upload permission sends video; read permission verifies the channel and checks processing. Google tokens select the destination channel: entering a channel ID is not a way to upload to an unrelated channel. Connecting a different channel to an already-bound profile is blocked; create a separate profile instead.

Every profile has an independent stored grant. Reconnecting preserves that profile's bound channel identity. Disconnect removes its local grant, without issuing an account-wide Google revocation that might disrupt other profiles using the same OAuth client. Google Account security settings can revoke the app globally when desired.

The global Google OAuth client JSON is reused for every profile; do not import it again when adding a channel. Select a saved profile and use **Connect YouTube channel**. Its connection section shows Connected, Disconnected or Reconnect required, plus the authorized channel title, handle when returned as an `@handle`, and channel ID. **Reconnect YouTube channel** renews the same channel's grant; **Disconnect** removes only this profile's local credentials. Missing or legacy custom URLs are not guessed into handles. Older profiles can reconnect to populate their handle. The channel lookup uses `channels.list(part=id,snippet, mine=true)` with that profile's new access token.

Two independent restrictions matter:

- An external OAuth app in **Testing** generally gets refresh tokens lasting seven days for these scopes. Moving the consent configuration to production and meeting applicable verification requirements avoids relying on short-lived testing grants. [Google OAuth expiration rules](https://developers.google.com/identity/protocols/oauth2).
- Uploads through unverified API projects created after July 28, 2020 can be restricted to **Private** until the project completes YouTube's audit. This is separate from the OAuth consent configuration. The app reports actual returned privacy. It cannot override an API restriction. [YouTube upload documentation](https://developers.google.com/youtube/v3/docs/videos/insert).

The uploader is not a rights-clearance tool. You remain responsible for recording/music rights and accurate audience/disclosure settings; YouTube may apply claims, restrictions or processing rejection independently of a successful API upload.

## Metadata Providers

Under **Metadata providers**, configure a name, HTTPS API base URL, model ID, API key, and JSON response mode. The backend appends `/chat/completions` to the base URL.

| Provider | Base URL | Model |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | A current model ID from your DeepSeek dashboard |
| OpenRouter | `https://openrouter.ai/api/v1` | The exact provider/model identifier from OpenRouter |
| Other compatible provider | Its HTTPS API base, often ending in `/v1` | That provider's model ID |

Use **JSON object** when supported; **Plain text JSON** omits `response_format` for compatible services/models that do not support it. The API also accepts a timeout of 5-180 seconds, default 90. Keys are stored server-side in the OS credential store. Editing an existing provider with an empty key keeps the old key.

The generator receives only filename, supplied recording context/transcript, language and channel style/default tags. Raw audio is not sent to the LLM. It does not transcribe, recognize songs, scrape lyrics or claim ownership. A meaningful filename and a sentence of recording context improve results; a transcript is optional. Model output cannot choose a channel, privacy, audience, disclosure or approval.

Responses must validate as `{title, description, tags}`. Validation includes 100 title characters, 5000 UTF-8 description bytes, and YouTube's combined tag limit (including separators/quoted spaces). Invalid responses get one correction attempt. Network/provider failures leave the rendered video available and an editable conservative draft. Update provider settings and regenerate, or simply enter your own metadata.

Compatible protocol references: [DeepSeek JSON mode](https://api-docs.deepseek.com/guides/json_mode/), [OpenRouter API](https://openrouter.ai/docs/quickstart).

## Profiles And Daily Use

Each profile saves: display name; verified channel ID/name; full visualizer/background/export preset; metadata provider; prompt/style; category ID (Music is `10`); default tags; language; Private/Unlisted default; kids and altered/synthetic defaults. No profile can default to Public.

Create a profile and connect it once. Choose it in the main studio, tune the visual editor, then use **Save current visual settings** to retain that look for future recordings. Ordinary **Save profile** preserves its existing visual preset. Selecting a profile applies its preset while preserving the current output filename. The last selected profile is remembered in that browser for that backend.

For a new recording, upload audio, select the channel, optionally supply recording facts, and press **Prepare for YouTube**. The pipeline snapshots the selected channel/configuration and does a full render, not the five-second preview. Profile edits do not retarget an in-progress job.

At review you can watch the actual MP4 and edit metadata, category and privacy. Verify **Made for kids** and **Altered or synthetic content**. The latter maps to YouTube `status.containsSyntheticMedia`; it concerns applicable altered/synthetic media, not merely whether an LLM assisted the description. Review the current YouTube disclosure guidance for your content. [API status fields](https://developers.google.com/youtube/v3/docs/videos).

Tick the review checkbox and choose **Approve & upload**. Public additionally requires its own checkbox. The backend binds approval to the exact artifact hash, channel, metadata and settings revision. Stale review submissions fail instead of uploading a different draft. Subscriber notifications are disabled for API uploads in this initial version.

## Editor Improvements

All previous controls, live-frame behavior and encoded previews remain:

- Composition presets place a centered ring, corner ring, horizontal bottom spectrum, or ring plus spectrum relative to your output dimensions.
- Undo/redo retains the latest 50 visual edits; rapid slider edits are grouped. Source files, channel connections and publishing actions are not undone.
- Duplicate a layer, tune minimum/maximum FFT frequency, and adjust its backdrop opacity for readability against bright clips.
- **Scale layers with resolution** preserves relative placement/size across resolution changes. Circular layers retain their proportions. Disable it for exact pixel-size behavior.
- Background clips have individual remove and reorder controls. The shared renderer scales/crops, sequences and loops them to match the audio duration; playback speed affects both preview and export.
- **Background only** hides visualizers in the editor request only. It never disables export layers. Scrub Frame time to inspect the generated/video background at another moment.
- **Framing guides** are a browser-only overlay; neither MP4 nor downloaded PNG contains guides.
- The PNG download is the backend-rendered full-resolution frame, before lossy encoding.

This remains a debounced exact still editor, not realtime video playback. Audio decoding and first-time normalization of background clips can take time. Response-scale/smoothing changes are recomputed from the audio history. For actual animation and compression, retain **Preview 5 seconds** and the **Rendered video** tab.

NVENC accelerates H.264 encoding when available. FFT analysis, OpenCV composition and background normalization still use CPU work; enabling a GPU does not make every stage GPU-based. Existing local-render controls remain available independently of publishing setup.

## Progress, Storage And Recovery

Jobs display original filename, profile/channel, creation time, stage, render percent and confirmed upload bytes. Upload completion returns `video_id` and `video_url`; processing is tracked separately before marking the job completed. Links and actual privacy remain in history after reload/restart.

| Data | Location |
|---|---|
| Uploaded source/background clips | `<media_root>/outputs/audio_video_uploads/` |
| Publishing MP4 | `<media_root>/outputs/audio_video/publish_<run-id>/<output-name>.mp4` |
| Ordinary render MP4 | Existing `<media_root>/outputs/audio_video/<run-id>/` |
| Live-preview cache | `<media_root>/outputs/audio_frame_cache/` |
| Profiles/providers/history/approval checkpoints | `%LOCALAPPDATA%/MangaNarrator/publishing/publishing.db` |
| Launcher port/PID | Same state directory, `launcher.json` |
| Google client, OAuth grants, LLM keys, session URLs, owner key | OS credential store via Python `keyring` |

`PUBLISHING_STATE_DIR` overrides the private state directory. It must be outside both the repository and media root. Do not share its database: although it contains no API keys/tokens, it includes metadata drafts, prompts, transcripts and publication history. Back up the database only with the server stopped, including SQLite sidecar files where present. A copied profile database needs credentials reconfigured on a different machine.

The worker persists state between stages. An interrupted render starts over; completed renders are reused. Metadata failures do not trigger rerendering. Uploads use fixed 8 MiB chunks, persisted session references and server-confirmed offsets; resumed sessions are queried before more bytes are sent. [YouTube resumable protocol](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol).

- Network failures, supported server failures and rate limits use bounded exponential backoff/jitter and honor Retry-After. After eight failures, manual retry is required.
- Expired access tokens refresh automatically. Revoked/missing refresh grants pause at **Needs reauth**; reconnect the same profile and retry.
- Quota/permission/invalid metadata failures are surfaced rather than retried endlessly.
- If YouTube rejects settings before an upload session exists, **Edit review** lets you correct the draft without rerendering. Once a session exists, review editing is blocked to avoid changing the approved upload midstream.
- An expired/missing session or uncertain completion enters **Needs attention**. Check YouTube Studio before explicitly restarting an upload. The YouTube insert API does not provide general exactly-once semantics; this application cannot safely infer that a lost completion response means no video exists.
- A known video ID is never automatically uploaded again. YouTube processing failures require investigation in YouTube Studio.
- Changed source files or rendered artifacts are rejected; prepare a fresh run rather than uploading an unreviewed replacement.

Local MP4s and source files are not automatically deleted. Canceling a job does not delete a YouTube video or erase local media. Do not remove files needed by pending jobs. Existing render jobs and publishing jobs have independent histories.

## API And Embedding

Publishing routes are under `/video/publishing`. Normal studio source upload is still `POST /video/audio/source` with multipart `audio_file=@recording.mp3`, returning `audio_ref`, original name and duration.

| Method / path below publishing prefix | Purpose |
|---|---|
| GET `/info` | Whether publishing is enabled / worker running |
| POST `/session` | Exchange owner authentication for an HttpOnly session |
| GET `/configuration`; POST `/configuration/google` | Setup status / import Google web client |
| GET/POST `/providers`; PATCH `/providers/{id}` | Provider configuration and securely stored key |
| GET/POST `/profiles`; PATCH/DELETE `/profiles/{id}` | Profile management |
| POST `/profiles/{id}/connect`, `/disconnect` | Authorize or locally disconnect a channel |
| GET `/oauth/callback` | Google authorization callback |
| POST `/runs` | Audio reference + profile + context/transcript + optional config |
| GET `/runs`, `/runs/{id}` | Recent runs / full status |
| PATCH `/runs/{id}/metadata` | Save reviewed draft with expected revision |
| POST `/runs/{id}/regenerate-metadata` | Regenerate without rerendering |
| POST `/runs/{id}/upload` | Approve exact review and queue upload |
| POST `/runs/{id}/retry` | Retry failed stage; explicit `confirm_restart` for uncertain sessions |
| POST `/runs/{id}/reopen-review` | Correct a failed draft before any upload session was initiated |
| POST `/runs/{id}/cancel` | Cancel a review/failed/attention run |
| GET `/runs/{id}/file?download=true` | Protected rendered MP4 |

Creating a run requires an `Idempotency-Key` header of 8-128 characters. Reusing it with different request data is rejected. Source names and presets are snapshots; full videos receive unique run directories. The React client retains a preparation key across duplicate clicks or uncertain HTTP responses with identical inputs.

Except `/info` and the state-validated OAuth callback, routes require owner bearer authentication or the studio session. API calls also require `X-Publishing-Client: studio`; MP4 playback uses the HttpOnly cookie. The new route namespace checks trusted Host/Origin values independently of legacy CORS. OAuth query parameters are removed from access logs. Secrets never appear in profile/run serialization.

For embedding, import `AudioVideoStudio` (complete editor) or `PublishPanel` (publishing only) from `frontend/src/index.js`. The main component supports `apiBase`, `publishingToken`, and `showPublishing` in addition to its existing callbacks. Prefer a same-origin reverse proxy and authenticated backend session; never bake owner tokens or provider keys into a frontend build. `PublishPanel` accepts `source`, `config`, and React-setter-compatible `onConfig`. The separate `PublishingClient` contains transport concerns, not rendering UI.

For frontend development, run `npm run dev` under `frontend/`; Vite proxies `/video` to port 8084. The launcher uses the built frontend for day-to-day operation. For remote integration, set `PUBLISHING_ENABLED=1`, explicit `PUBLISHING_ORIGINS` and `PUBLISHING_REDIRECT_URI`; use HTTPS and a protected, same-origin deployment. This extension is not a multi-tenant account/permission system. Do not expose the existing unauthenticated MangaNarrator routes directly to the internet.

## Verification

```powershell
conda activate manganarrator-video
pip install -r requirements-publishing.txt
python -m unittest discover -s tests -v
cd frontend
npm run build
npm run test:e2e
```

Start the studio before browser tests. `STUDIO_URL` overrides the Playwright base URL; otherwise it uses `http://127.0.0.1:8084/studio/`. Python publishing tests use fake credentials and network transports. Browser publishing tests mock Google/LLM workflow responses while exercising the actual React review interaction and local renderer. Tests do not upload to real channels or bill an LLM provider.

A real acceptance test still requires your Google OAuth configuration, channel consent and provider API key: prepare a short recording, approve a Private upload, interrupt the network during a longer upload if desired, and verify the final channel ID/link and playback in YouTube Studio. No real upload is performed by installation or startup.
