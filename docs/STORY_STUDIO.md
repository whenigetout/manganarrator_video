# Story Studio — first production slice

**Windows / Conda:** [Simple launch and missing-contracts repair guide](CONDA_LAUNCH.md). Audio and Story use one server; both Windows launcher names now start the same app.

Story Studio is available alongside Audio Studio at **`/studio/#story`**. Use the top Studio switcher. The existing manga and audio APIs remain available.

## What works

- Import the explicit structured Markdown format below, or normalized `StoryProject` JSON.
- Browse series → arc → chapter → scene; edit narration, dialogue, speaker, voice label, emotion, delivery and pauses independently.
- Preserve canonical scene text separately from the production draft. Canon is read-only after import.
- Save revisions, undo unsaved edits, restore an earlier saved revision as a new revision, duplicate drafts and lock scenes.
- Import/replace a speech take for one segment. Other takes remain attached; old takes stay in the project history/assets.
- Decode imported audio to 48 kHz stereo PCM and measure it with FFprobe. Text/voice/emotion/delivery changes flag the old take as stale.
- Upload/reuse still images; write visual prompts without an image service; use contain/cover, a subtle zoom, and fades through black.
- Display separate measured speech, visual and sound-bed tracks. Automatic shots reflow; manual placements retain their scene-relative seconds. Gaps, overlaps, stale takes and uncovered scenes block export.
- Add silence and per-line pauses; mix imported music, ambience or SFX with gain, looping and fades.
- Preview one selected scene or render a selected chapter to MP4. Download a production manifest recording the exact revision, measured tracks, assets and render settings.
- Rendering never triggers publishing.

The first slice imports speech rather than calling the manga-shaped TTS API. Voice labels and directions are production metadata for the recording/TTS tool you choose. Adaptation controls save an editorial brief; they do **not** claim to run automatic rewriting. There is no image-generation dependency, automatic raw-chat conversion, drag-to-edit timeline, cross-dissolve, waveform editor or integrated story publishing button yet.

## Setup

Use Python 3.11+ and Node compatible with the existing Vite version. Install FFmpeg and FFprobe on PATH. From this repository:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-story.txt
python -m pip install --upgrade "git+https://github.com/whenigetout/manganarrator_contracts.git#subdirectory=python"
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn video_server:app --host 127.0.0.1 --port 8084
```

Open `http://127.0.0.1:8084/studio/#story`. Use one API worker. Set `media_root` in `config.yaml` to a valid absolute directory on your machine (the checked-in example is a Windows path). `config.yaml` continues to control the existing manga/audio media root. Story data defaults to `<media_root>/outputs/story_studio`; optionally set `STORY_STUDIO_ROOT` to an absolute private directory before launch. It holds project JSON, immutable revision snapshots, normalized assets and render outputs. Back up that directory, not just Git.

If an existing Windows Audio Studio environment is already installed, install `requirements-story.txt`, upgrade contracts as above, then use the existing **Launch Studio.cmd** and select Story Studio. Windows launcher execution was not tested in the Linux validation environment. The launcher enables the existing publishing feature, but does not upload anything by itself.

Do not expose this local, unauthenticated editor to the internet. The story API is intended for a single local user, like the existing media editor.

## First scene walkthrough

1. Import `fixtures/story-demo.md`, or a private production JSON prepared separately. Never commit a private manuscript to this public repo.
2. In **Manuscript**, edit production lines and Save draft. The canonical pane remains unchanged.
3. In **Voices**, set directions/voice labels first, then import a WAV/MP3/FLAC/OGG/M4A/AAC take for each spoken line. Each upload is limited to 100 MB. Replacing one take measures its new length and updates subsequent timing.
4. In **Visuals**, add a shot and upload a PNG/JPEG/WebP image. One automatic shot covers the whole scene; several divide its measured duration equally. You can switch a shot to manual timing and edit its start/duration. Those edits will not be silently overwritten.
5. In **Timeline**, resolve listed conflicts. Optionally import a sound bed and add it to the scene. All sound-bed times are scene-relative; the chapter timeline displays their absolute chapter positions.
6. In **Export**, choose Preview scene or Render chapter. The preview can render a complete selected scene even if other scenes still lack takes. Download MP4 and manifest when complete.

Keep licensed audio and image usage records with your project. No API keys or external services are necessary for these steps.

## Structured Markdown v1

The importer is deliberately explicit. It rejects unsupported prose or chat lines instead of silently discarding instructions or treating them as fictional dialogue.

```markdown
# Series title {#series-id}
## Arc title {#arc-id}
### Chapter title {#chapter-id}
#### Scene title {#scene-id}
[line-001] NARRATOR: A lantern moved behind the gate.
[line-002] KEEPER: Someone is still outside.
[line-003] PAUSE: 0.5
```

Headings require stable `{#id}` markers; segment IDs are explicit and unique across the project. Dialogue character IDs create character entries. All other nonblank lines are rejected. Use JSON for richer metadata, source references, prewritten canonical text, visual prompts and manual placement. JSON Schema: `GET /video/story/schema`, or `schemas/story-v1.schema.json` in the contracts repository. Pydantic additionally validates uniqueness, cross-references and conditional timing rules.

**Manuscript JSON** exports text and shot plans without local asset bindings so it can be imported as a new project. To retain uploaded media within this installation use **Duplicate draft**. The production manifest is an audit record, not a self-contained media archive; back up the project directory to move media between machines. A future portable ZIP importer is still needed.

## Timing and preservation rules

The audio asset registry is server-owned. Imported JSON cannot inject file paths or fabricated durations. Audio is decoded once and measured; export rechecks hashes and measured durations before use. Word counts are never used to render.

A speech fingerprint includes text, kind, character, effective voice, emotion and direction. Editing them preserves the old take but blocks export until a matching new take is imported. Changing a pause does not invalidate the recording.

Automatic shots may use an inclusive `start_segment_id` / `end_segment_id` range in JSON. Without anchors, automatic shots divide scene time equally. Manual shots use `start` and `duration` in seconds; automatic reflow does not modify them. Preview reports coverage conflicts. Changing a locked scene, its voice assignments or its source fails; unlock and save first. Restoring history also respects locks and retains later imported assets.

The renderer rounds visual boundaries to output frames while retaining the measured audio clock. Expected container duration tolerance is one video frame plus codec padding. Fades are through black, not overlapping cross-dissolves. CPU `libx264` is selected explicitly for this first slice; Audio Studio keeps its own existing NVENC/CPU behavior.

## API map

All routes begin `/video/story`:

| Method / path | Purpose |
| --- | --- |
| `GET /schema` | Runtime JSON Schema |
| `GET /projects` | Local projects |
| `POST /import` | `{format: "markdown"|"json", content: string}` |
| `GET/PUT /projects/{id}` | Read / save a full validated project; `revision` is an optimistic concurrency guard |
| `GET /projects/{id}/history` | Saved revision numbers |
| `POST /projects/{id}/restore` | `{revision, restore_revision}` |
| `POST /projects/{id}/duplicate` | `{revision}`; copy local assets into a separate draft |
| `POST /projects/{id}/assets` | Multipart `file`, `kind`, `revision`, optional `segment_id` |
| `GET /projects/{id}/assets/{asset_id}` | Serve registered image/audio only |
| `GET /projects/{id}/timeline` | Optional `chapter_id`, `scene_id` filters |
| `POST /projects/{id}/render` | `{revision, chapter_id, scene_id?, width?, height?, fps?}` |
| `GET /projects/{id}/renders` | Previous jobs for this project |
| `GET /projects/{id}/renders/{job_id}/episode.mp4` | Completed video; `?download=true` forces download |
| `GET /projects/{id}/renders/{job_id}/manifest.json` | Completed production manifest |

Job status reuses `GET /video/status/{job_id}`, SQLite jobs and the existing audio render lock. Interrupted story renders become failed on startup and must be resubmitted. Render snapshots are immutable: editing the project while a render is queued does not change that render's revision.

## Verification

```bash
python -m pip install -r requirements-publishing.txt
python -m unittest discover -s tests -v
cd frontend
npm run build
# Requires the API running, configured media directories, and Chrome:
npm run test:e2e -- story.spec.js
```

`tests/test_story.py` covers importer rejection, stable IDs, schema/reference checks, real FFprobe timings, replacing one take, stale audio, manual timing preservation, locks, immutable source, optimistic revisions, history, duplication, scoped previews, API behavior, and real FFmpeg MP4 export. Existing suites cover Audio Studio and mocked publishing. See `docs/PROJECT_CONTEXT.md` for actual run results and limitations.
