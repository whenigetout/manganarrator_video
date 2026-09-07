"""Single-frame editor previews using the export compositor, before video compression."""
import hashlib
import json
import math
import subprocess
import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from app.audio_spectrum import SAMPLE_RATE, Spectrum, compose_frame, prepare_background
from app.models.domain import AudioVisualizerConfig

CACHE_LOCK = threading.Lock()
ANALYSIS_FIELDS = ("frequency_bins", "gain", "scale", "smoothing", "min_frequency", "max_frequency")


def fingerprint(path):
    info = path.stat()
    return str(path.resolve()), info.st_size, info.st_mtime_ns


def cache_folder(builder, key):
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    folder = Path(builder.config.media_root) / "outputs" / "audio_frame_cache" / digest
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def cached_audio(builder, ref):
    path = Path(ref.resolve(Path(builder.config.media_root)))
    folder = cache_folder(builder, fingerprint(path))
    pcm = folder / "audio.f32"
    with CACHE_LOCK:
        if not pcm.exists():
            pending = folder / "pending.f32"
            result = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "2",
                                     "-ar", str(SAMPLE_RATE), "-f", "f32le", str(pending)], capture_output=True)
            if result.returncode or not pending.exists() or not pending.stat().st_size:
                pending.unlink(missing_ok=True)
                raise ValueError("Audio could not be decoded for the editor")
            pending.replace(pcm)
    return pcm, pcm.stat().st_size / (4 * 2 * SAMPLE_RATE)


@lru_cache(maxsize=1)
def demo_samples():
    t = np.arange(SAMPLE_RATE * 5, dtype=np.float32) / SAMPLE_RATE
    signal = sum(.12 / (i + 1) * np.sin(2 * np.pi * frequency * t) *
                 (.55 + .45 * np.sin(t * (i + 2))) for i, frequency in enumerate((80, 180, 440, 1000, 2400, 6000)))
    return np.stack([signal, signal], axis=1).astype(np.float32)


@lru_cache(maxsize=128)
def levels_at(pcm_path, signature, frame_index, fps, analysis):
    samples = np.memmap(pcm_path, dtype=np.float32, mode="r").reshape(-1, 2) if pcm_path else demo_samples()
    try:
        spectrum = Spectrum(AudioVisualizerConfig(**dict(zip(ANALYSIS_FIELDS, analysis))), fps)
        # Replay from frame zero, including release state, exactly as the export does.
        for index in range(frame_index + 1):
            levels = spectrum.at(samples, index / fps)
        return levels.copy()
    finally:
        if pcm_path:
            samples._mmap.close()


def background_at(builder, request, frame_index, duration):
    rc = request.render_config
    media = [fingerprint(Path(ref.resolve(Path(builder.config.media_root)))) for ref in request.background.media_refs]
    key = [media, rc.viewport_w, rc.viewport_h, rc.fps, request.background.playback_rate, duration]
    folder = cache_folder(builder, key)
    manifest = folder / "clips.txt"
    with CACHE_LOCK:
        if not manifest.exists():
            prepare_background(builder, request, folder, duration)
    # Use the normalized, looped sequence shared with export. Selecting by index
    # preserves the exact frame at clip boundaries even when source FPS differ.
    result = subprocess.run(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-f", "concat", "-safe", "0",
                             "-i", str(manifest), "-vf", f"select=eq(n\\,{frame_index})", "-frames:v", "1",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, timeout=120)
    if result.returncode or len(result.stdout) != rc.viewport_w * rc.viewport_h * 3:
        raise ValueError("Unable to read background frame")
    return np.frombuffer(result.stdout, np.uint8).reshape(rc.viewport_h, rc.viewport_w, 3)


def render_preview_frame(builder, request, seconds, demo=False):
    rc = request.render_config
    if demo:
        pcm, duration, signature = None, 5, ()
    else:
        pcm, duration = cached_audio(builder, request.audio_ref)
        signature = fingerprint(pcm)
    index = min(math.floor(seconds * rc.fps), max(0, math.ceil(duration * rc.fps) - 1))
    timestamp = index / rc.fps
    energies = [levels_at(str(pcm) if pcm else None, signature, index, rc.fps,
                          tuple(getattr(viz, key) for key in ANALYSIS_FIELDS))
                for viz in request.visualizers if viz.enabled]
    background = background_at(builder, request, index, duration) if request.background.mode == "media" else None
    return compose_frame(builder, request, timestamp, energies, background), timestamp


def preview_png(builder, request, seconds, demo=False):
    frame, timestamp = render_preview_frame(builder, request, seconds, demo)
    ok, encoded = cv2.imencode(".png", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_PNG_COMPRESSION, 1])
    if not ok:
        raise ValueError("Could not encode the preview frame")
    return encoded.tobytes(), timestamp
