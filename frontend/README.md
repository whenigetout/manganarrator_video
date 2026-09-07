# Audio Video Studio

React + Vite frontend for the [MangaNarrator video backend](https://github.com/whenigetout/manganarrator_video).

Upload audio once, edit a live backend-rendered still, render a short video preview or full export, and find completed renders by recording filename. The live editor and rendered-video player are separate views.

## Run Locally

The updated MangaNarrator video backend must be running on port 8084.

```sh
npm ci
npm run dev
```

Open the URL printed by Vite (normally http://127.0.0.1:5173). The development proxy forwards `/video` to http://127.0.0.1:8084. For a different backend, enter its URL in the app and click the plug button, or set `VITE_API_BASE` in `.env.local`.

For the backend's integrated /studio/ page:

```sh
npm ci
npm run build
```

The backend serves `dist/` at http://127.0.0.1:8084/studio/. Build output is not committed; rebuild after pulling frontend changes. Vite uses a relative asset base, so the build works under another URL prefix too.

## Editor Workflow

- Select MP3/WAV audio. The source uploads once and returns a reusable MediaRef.
- The **Live editor** updates after edits, without creating a render job. Select **Frame time** to inspect another audio timestamp.
- **Spectrum**, **Background** and **Export** tabs contain the controls. Resolution changes preserve layer dimensions in pixels, making the relative-size change visible.
- Before selecting audio, a labeled demo audio frame is shown.
- **Preview 5 seconds** renders a short video at the chosen export settings. **Rendered video** remains available while you edit the still.
- **Render video** renders the full track.
- Jobs show source filename, output filename, type, dimensions, FPS, layouts and creation time. Filter by filename or ID. UUIDs are still available under **Job ID**.
- Configuration JSON supports import/export. Source media and completed videos live on the backend.

The still uses the exact export compositor at full resolution, including audio analysis and smoothing history. It precedes video compression; the video preview shows the encoded result. Color/position changes reuse cached analysis. Requests debounce for 180 ms and stale responses cannot overwrite newer settings. New audio decoding and video-background preparation may take longer.

## Embed In React Or Next.js

Copy `src/` into your host application, retaining its module structure. The host needs `react`, `react-dom` and `lucide-react`. It supplies its own bundler; Vite is only needed to develop this standalone app.

```jsx
import { AudioVideoStudio } from './audio-studio';

export default function AudioPage() {
  return (
    <AudioVideoStudio
      apiBase="http://127.0.0.1:8084"
      onRenderStarted={(job) => console.log(job.job_id)}
      onRenderCompleted={(job) => console.log(job.result)}
    />
  );
}
```

`src/index.js` exports the editor and imports scoped styles. The component uses a `"use client"` boundary for Next.js App Router. If supplying event callbacks from Next.js, make the containing component a client component too. For Next.js Pages Router, move the global CSS import to your `_app` entry if your setup requires it.

Props:

| Prop | Default | Purpose |
| --- | --- | --- |
| `apiBase` | empty string | Backend URL; empty means same-origin. |
| `initialConfig` | built-in defaults | Initial configuration overrides. |
| `onRenderStarted` | omitted | Receives the created job. |
| `onRenderCompleted` | omitted | Receives the completed selected job. |

The CSS selectors are scoped under `.audio-studio` so controls do not restyle the host app. For remote integration, use the host's authentication/CORS policy. The local backend already enables CORS.

For a custom interface, import only the API client:

```javascript
import { AudioVideoClient } from './audio-studio/api';
const client = new AudioVideoClient('http://127.0.0.1:8084');
const source = await client.uploadSource(file);
const config = { ...settings, audio_ref: source.audio_ref, source_name: source.name };
const frame = await client.frame(config, 2, false);
const imageUrl = URL.createObjectURL(frame.blob); // revoke when replaced
const job = await client.render(config);
const status = await client.status(job.job_id);
```

## Source Map

- `AudioVideoStudio.jsx`: editor state, uploads, preview modes and render lifecycle.
- `SettingsPanel.jsx`: spectrum, background and export controls.
- `JobList.jsx`: readable/searchable render history and downloads.
- `useLiveFrame.js`: debouncing, cancellation and stale-response protection.
- `api.js`: backend client, independent of React.
- `config.js`: defaults and request construction.
- `studio.css`: scoped styling.

## Checks

```sh
npm run build
npm run test:e2e
npm run format
```

Browser tests use a locally running backend and installed Chrome. Set `STUDIO_URL` to change the page URL or `PLAYWRIGHT_CHANNEL` to another installed Playwright browser channel. Test recordings are generated in memory.

The Python renderer tests and complete configuration guide live in the backend repository. This frontend is maintained there under `frontend/`; publish frontend updates from the backend checkout with:

```sh
git subtree push --prefix=frontend studio-frontend main
```
