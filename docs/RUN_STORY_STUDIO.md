# Run Story Studio without the Windows renderer

Both options use the same preparation editor from GitHub. Choose one host for your projects. Your tablet and desktop should open that host's store. To move between hosts, stop edits and migrate the full project directory once.

## Option A · Private Story Studio on Railway

[Railway Free](https://docs.railway.com/pricing/free-plan) currently includes a 0.5 GB persistent volume and $1 in monthly usage credit. This is suitable for trying a small personal workspace. Image-heavy projects or usage above the allowance can exhaust the free tier. The service can sleep. Check Railway's plan and usage before depending on it, and keep a separate backup.

1. In your own Railway account, connect this GitHub repo and deploy the `main` branch. Railway can build the root `Dockerfile`. Keep a single replica.
2. Attach a persistent volume at `/data`. The container defaults `STORY_STUDIO_ROOT` to `/data` and refuses to start without the mount. Set `STORY_BROWSER_PASSWORD` in Railway variables to a long, randomly generated password. Set `STORY_SHARED_TOKEN` to a separate random secret if using the locally running Windows app.
3. Generate an HTTPS domain under the service's networking settings. Open it on the tablet and PC, then sign in with username `story` and your browser password. The URL is reachable over the internet, but the page, projects and images all require authentication. Use HTTPS only.
4. For local Windows access through the existing app, set `STORY_SHARED_URL` to that HTTPS origin and `STORY_SHARED_TOKEN` to the API secret, then open `/studio/#story`.
5. After deploying, verify that anonymous requests return 401. Create a synthetic project, edit it from a second browser, then redeploy and confirm it survives. GitHub deployments update code. The mounted volume retains the story data.

A Railway account and GitHub connection are required. The container and volume checks do not select or change your billing plan.

### Open, close, or delete a project

Story Studio starts in the Library. Open a project to show its Manuscript and Visuals sections. Choose Library again to save pending edits and close the editor. Use **Delete project** on a Library card to remove it from normal access. The server retains the project files. To recover a deleted project, stop the service and remove the `.deleted` marker from that project's folder in the configured project root, then restart the service.

## Option B · Run on your Android tablet or phone

This uses [Termux](https://github.com/termux/termux-app#installation) with a [Debian PRoot environment](https://github.com/termux/proot-distro). Debian supplies the Linux ARM64 Python dependencies and a compatible Node version on devices such as the Galaxy Tab S9 FE+. Android does not need root. The preparation editor needs no FFmpeg, OCR or TTS.

Install Termux, then run these commands in Termux once:

```sh
pkg update
pkg install proot-distro
proot-distro install debian:trixie --name story-debian
proot-distro login story-debian
```

Run these in Debian:

```sh
apt update
apt install -y git ca-certificates python3 python3-venv nodejs npm
git clone https://github.com/whenigetout/manganarrator_video.git
cd manganarrator_video
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-preparation.txt
.venv/bin/python scripts/sync_contracts.py
npm --prefix frontend ci
npm --prefix frontend run build:preparation
./scripts/run_story_preparation.sh
```

Open [Story Studio on localhost](http://127.0.0.1:8085/) in the Android browser. Keep the Termux session running while editing. This works offline after installation and the build. The launcher binds to loopback and defaults to `$HOME/story-studio-projects` inside Debian. Back up that directory outside Termux before uninstalling or removing the Debian environment.

Next time, log into `story-debian`, enter the repository and run the launcher again. To update, stop the launcher, run `git pull --ff-only`, rerun the dependency and build commands, then restart. Project files stay in the same directory.

### Open the tablet's projects from Windows

Install [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools), enable USB debugging on the tablet, and authorize your own PC. With the tablet's server running, connect it over USB and run:

```powershell
adb forward tcp:8085 tcp:8085
```

Open [Story Studio on localhost](http://127.0.0.1:8085/) in the Windows browser. You are editing the tablet's actual projects. Unplugging the tablet removes Windows access until reconnected. When finished, remove the forward with `adb forward --remove tcp:8085`. Keep USB debugging authorization limited to your own PC.

To use the locally launched Windows Studio instead of the browser shortcut, set `STORY_SHARED_TOKEN` and `STORY_BROWSER_PASSWORD` privately in the tablet server's environment, then restart it. Configure the same API token and `STORY_SHARED_URL=http://127.0.0.1:8085` for the Windows Studio. Local rendering stays separate. [Shared configuration](SHARED_STORY_STUDIO.md).
