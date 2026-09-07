# Audio Video Studio

Portable audio-to-video frontend for the [MangaNarrator video backend](https://github.com/whenigetout/manganarrator_video). Upload recorded audio, configure radial or linear spectrum layers, render a five-second preview, and track or download completed video jobs.

![Radial spectrum sample](preview.png)

## Run

This repository is the frontend only. It needs the updated MangaNarrator video backend running locally.

When served by that backend, open http://127.0.0.1:8084/studio/.

For a standalone checkout:

```powershell
python -m http.server 5173 --bind 127.0.0.1
```

Open http://127.0.0.1:5173/, enter `http://127.0.0.1:8084` in the backend URL field, and click **Connect**. Serve the files over HTTP; ES modules do not work reliably from a file:// page.

Choose an MP3 or WAV, adjust spectrum settings, click **Preview 5 seconds**, then **Render video**. View progress and errors under **Render jobs**. Completed jobs include playback and download actions. The JSON editor supports preset import/export.

## Embed

Copy these files into your host application's public assets directory:

- `studio.js`
- `studio.css`
- `api.js`
- `preview.png`

Load and mount:

```html
<script type="module" src="/audio-studio/studio.js"></script>
<audio-video-studio api-base="http://127.0.0.1:8084"></audio-video-studio>
```

Omit `api-base` when the backend is on the same origin. The component uses Shadow DOM for CSS isolation, relative module asset URLs and no build-time environment variables. The backend must allow requests from the frontend origin. The local MangaNarrator backend already enables CORS; use your deployment's auth/CORS policy when integrating remotely.

Events bubble across the shadow boundary:

```javascript
const studio = document.querySelector('audio-video-studio');
studio.addEventListener('render-started', event => console.log(event.detail.job_id));
studio.addEventListener('render-completed', event => console.log(event.detail.result));
```

To build a different interface, use just the API client:

```javascript
import { AudioVideoClient } from './api.js';
const client = new AudioVideoClient('http://127.0.0.1:8084');
const job = await client.render(audioFile, configuration);
const status = await client.status(job.job_id);
const recent = await client.jobs();
const videoUrl = client.fileUrl(job.job_id);
```

The backend retains source audio and rendered files. The frontend transfers files through multipart requests and displays the backend's result; it does not perform the final export in the browser.

## Backend Routes

`POST /video/build/audio_upload`, `GET /video/status/{id}`, `GET /video/audio/jobs`, `GET /video/audio/jobs/{id}/file`, `POST /video/audio/background`, and `GET /video/audio/capabilities`.

The rendering engine and Python regression tests live in the backend repository. This frontend is also maintained there under `frontend/`. Publish frontend updates from that repository with:

```powershell
git subtree push --prefix=frontend studio-frontend main
```

The host backend's README documents output locations, configuration fields, FFT processing and GPU encoding.
