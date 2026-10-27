# Launch Studio with Conda on Windows

Audio Studio and Story Studio share one FastAPI server and one React application.
Use **Launch Studio.cmd**. `run_video_server.bat` now forwards to that same launcher for compatibility. Do not run both. `Launch Studio Dev.cmd` is for frontend development with a separate Vite terminal; it is unnecessary for normal testing.

## One-time repair / setup

Open **Anaconda Prompt** (or Miniconda Prompt), then run:

```bat
conda activate manganarrator-video
cd /d "E:\Getting myself out\manganarrator\manganarrator_video"
git pull --ff-only
python --version
python -m pip install -r requirements-story.txt
python scripts\sync_contracts.py --force
python -c "from mn_contracts.story import StoryProject; print('Story contracts OK')"
"Launch Studio.cmd"
```

Python must be 3.11 or newer. If your existing environment is older, create a separate environment with `conda create -n manganarrator-studio python=3.11 pip`, activate it, and run the same install commands. Keep the old environment for any other workloads.

Git is required for the contracts installation. Node.js 20.19+ or 22.12+ and FFmpeg/FFprobe must be on PATH. The launcher builds the frontend and installs its dependencies when needed. It also checks optional publishing dependencies; startup does not upload anything. Set `media_root` in `config.yaml` to a real absolute directory on your machine.

## Every subsequent launch

```bat
conda activate manganarrator-video
cd /d "E:\Getting myself out\manganarrator\manganarrator_video"
"Launch Studio.cmd"
```

The browser opens automatically. Select Story Studio in the top switcher, or use `/studio/#story` on the port printed in the console (normally8084). Keep the console open; Ctrl+C stops the server. If the port is busy the launcher may select another one.

Python selection: `STUDIO_PYTHON` override, then your active Conda environment, then the standard user Miniconda/Anaconda `manganarrator-video` locations. Launching from an activated prompt supports Conda installed on another drive. The log prints the exact Python path. For double-click use with a custom Conda installation, set `STUDIO_PYTHON` to that environment's full `python.exe` path.

## Why the missing-module error happened

`mn_contracts` was installed, but that copy lacked the new `story` module. The launcher now probes `from mn_contracts.story import StoryProject` with the selected Python. If unavailable, it reinstalls a tested contracts revision and checks again before starting the server. A healthy installation does not download contracts on every launch. An install failure stops startup instead of continuing into a traceback. `sync_contracts.py --force` forces a repair.

If the import still fails, inspect `python -c "import mn_contracts; print(mn_contracts.__file__)"`; a local folder with the same name can shadow the installed package. Logs are under `local_tmp/logs`.

## API-only development

For deliberate backend-only hot reload, after setup:

```bat
python -m uvicorn video_server:app --host 127.0.0.1 --port 8084 --reload
```

This does not build the frontend or initialize the Studio launcher's publishing settings. Use the normal launcher for testing the complete UI. Never run two servers against the same Story Studio data directory.

## First smoke check

Open Story Studio, import `fixtures/story-demo.md`, and confirm scenes appear. Missing media warnings are expected until you import takes and images. Then follow `docs/STORY_STUDIO.md` for preview/export. Back up the private story-data directory before moving environments or machines.

The Python contracts repair paths and backend were exercised on Linux. Windows CMD/PowerShell and your actual Conda environment still require the first local launch; they cannot be verified from the remote Linux workspace.
