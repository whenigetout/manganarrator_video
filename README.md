# Manga Narrator Video Backend

FastAPI backend for rendering MangaNarrator video outputs with FFmpeg. The existing OCR-run video pipeline is still supported, and the backend now also includes an audio-first workflow for quickly generating YouTube-ready visualizer videos from a recorded audio file.

## Audio Visualizer Videos

Use this feature when you have an audio file, such as a song recording or narration track, and want a configurable MP4 video with:

- a generated abstract animated background, or one or more background video clips
- reactive visualizers generated from the actual audio stream
- circular, horizontal, or vertical visualizer layouts
- configurable resolution, FPS, colors, size, position, opacity, and output filename

The build runs through the existing job system. Start a build, poll `/video/status/{job_id}`, then use the returned `MediaRef` to find the generated MP4.

### Output Location

The backend reads `media_root` from `config.yaml`. In the current local config:

```yaml
media_root: "E:/pcc_shared/manga_narrator_runs"
```

Uploaded audio files are saved under:

```text
E:/pcc_shared/manga_narrator_runs/outputs/audio_video_uploads/
```

Generated videos are saved under:

```text
E:/pcc_shared/manga_narrator_runs/outputs/audio_video/{run_id}/{output_name}
```

If `run_id` is omitted, the backend creates one like `audio_video_abc123...`.

### Start The Backend

From the repo root, activate the environment and run the server as usual. For example:

```powershell
conda activate <your-env-name>
pip install -r requirements.txt
uvicorn video_server:app --host 127.0.0.1 --port 8000 --reload
```

`python-multipart` is required for the upload endpoint and is now included in `requirements.txt`.

### Quick Test With An Uploaded Audio File

Create a config file, for example `audio_video_config.json`:

```json
{
  "run_id": "my_song_test",
  "output_name": "my_song_visualizer.mp4",
  "render_config": {
    "viewport_w": 2560,
    "viewport_h": 1440,
    "fps": 30,
    "vcodec": "h264_nvenc",
    "pix_fmt": "yuv420p",
    "acodec": "aac",
    "audio_bitrate": "192k",
    "verbose": true
  },
  "background": {
    "mode": "generated",
    "generated_style": "aurora",
    "color_a": "#111827",
    "color_b": "#ec4899",
    "color_c": "#22d3ee",
    "blur": 28,
    "playback_rate": 1.0
  },
  "visualizers": [
    {
      "enabled": true,
      "kind": "circular",
      "position": "bottom_right",
      "width": 460,
      "height": 460,
      "margin_x": 96,
      "margin_y": 96,
      "opacity": 0.95,
      "colors": "0x22d3ee|0xec4899|0xfacc15|0xa78bfa",
      "scale": "sqrt",
      "frequency_bins": 96,
      "gain": 1.0
    },
    {
      "enabled": true,
      "kind": "horizontal",
      "position": "bottom",
      "width": 1800,
      "height": 220,
      "margin_y": 72,
      "opacity": 0.9,
      "colors": "0x22d3ee|0xec4899|0xfacc15|0xa78bfa",
      "mode": "bar",
      "scale": "sqrt",
      "frequency_bins": 128,
      "gain": 1.0
    }
  ]
}
```

Start a build with PowerShell:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/video/build/audio_upload" `
  -F "audio_file=@C:\path\to\your_recording.wav" `
  -F "config_json=<audio_video_config.json"
```

The response contains a job id:

```json
{
  "status": "processing",
  "job_id": "..."
}
```

Poll the job:

```powershell
curl.exe "http://127.0.0.1:8000/video/status/<job_id>"
```

When it is done, the response contains a `MediaRef` for the generated video. With the example config above, the file should be at:

```text
E:/pcc_shared/manga_narrator_runs/outputs/audio_video/my_song_test/my_song_visualizer.mp4
```

### Build From An Existing MediaRef

If the audio file is already under `media_root`, you can call the JSON endpoint directly:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/video/build/audio" `
  -H "Content-Type: application/json" `
  -d @request.json
```

Example `request.json`:

```json
{
  "audio_ref": {
    "namespace": "outputs",
    "path": "audio_video_uploads/my_recording.wav"
  },
  "run_id": "existing_audio_test",
  "output_name": "existing_audio_visualizer.mp4"
}
```

### Use Background Video Clips

Set `background.mode` to `media` and pass one or more `media_refs`. The backend repeats the clips as needed and trims the final video exactly to the audio duration.

```json
{
  "background": {
    "mode": "media",
    "media_refs": [
      {
        "namespace": "outputs",
        "path": "backgrounds/clip_01.mp4"
      },
      {
        "namespace": "outputs",
        "path": "backgrounds/clip_02.mp4"
      }
    ],
    "playback_rate": 1.0
  }
}
```

The background video is scaled to fill the configured output resolution, cropped to fit, repeated if the audio is longer, and trimmed at the audio end.

### Customization Reference

`render_config` controls the final video container and encoding:

- `viewport_w`, `viewport_h`: output resolution. Default for this feature is `2560x1440`.
- `fps`: output frame rate. Default is `30`.
- `vcodec`: video encoder, for example `h264_nvenc` or `libx264`.
- `pix_fmt`: usually `yuv420p` for upload-friendly MP4.
- `acodec`: audio encoder, usually `aac`.
- `audio_bitrate`: output audio bitrate, for example `192k` or `320k`.
- `verbose`: whether FFmpeg logs are printed.

`background` controls the base video:

- `mode`: `generated` or `media`.
- `generated_style`: `aurora`, `nebula`, `gradient`, or `plasma`.
- `color_a`, `color_b`, `color_c`: hex colors used by generated backgrounds.
- `blur`: blur amount for generated abstract motion.
- `media_refs`: background clips when `mode` is `media`.
- `playback_rate`: speed multiplier for background media.

Each item in `visualizers` controls one reactive overlay:

- `enabled`: turn the visualizer on or off.
- `kind`: `circular`, `horizontal`, or `vertical`.
- `position`: `center`, `top_left`, `top_right`, `bottom_left`, `bottom_right`, `top`, `bottom`, `left`, or `right`.
- `width`, `height`: visualizer size in pixels.
- `margin_x`, `margin_y`: distance from the selected edge.
- `opacity`: overlay opacity from `0.0` to `1.0`.
- `colors`: FFmpeg color list, for example `0x22d3ee|0xec4899|0xfacc15`.
- `mode`: bar style for horizontal/vertical visualizers: `bar`, `line`, or `dot`.
- `scale`: amplitude scale: `lin`, `sqrt`, `cbrt`, or `log`.
- `frequency_bins`: affects frequency resolution/window size.
- `gain`: boosts or lowers visualizer reactivity.
- `background_opacity`: keep at `0.0` for transparent visualizer backgrounds.

### Notes

- Visualizers are generated from the uploaded audio with FFmpeg audio analysis filters. They are not pre-rendered overlay clips.
- The JSON endpoint expects the audio to already exist under `media_root` and be addressable by `MediaRef`.
- The upload endpoint is the easiest path for local testing because it saves the audio and starts the build in one request.
- If your machine does not have NVENC available, set `render_config.vcodec` to `libx264` for CPU encoding.
