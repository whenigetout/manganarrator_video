"""Audio spectrum frames: NumPy FFT, OpenCV rasterization, FFmpeg/NVENC export."""
import math
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np


SAMPLE_RATE = 44100
FFT_SIZE = 4096


def rgb(color):
    color = color.removeprefix("#").removeprefix("0x")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


class Spectrum:
    def __init__(self, config, fps):
        self.config = config
        self.window = np.hanning(FFT_SIZE).astype(np.float32)
        frequencies = np.fft.rfftfreq(FFT_SIZE, 1 / SAMPLE_RATE)
        edges = np.geomspace(config.min_frequency, config.max_frequency, config.frequency_bins + 1)
        self.bands = [np.flatnonzero((frequencies >= a) & (frequencies < b)) for a, b in zip(edges[:-1], edges[1:])]
        self.centers = np.sqrt(edges[:-1] * edges[1:])
        self.frequencies = frequencies
        self.levels = np.zeros(config.frequency_bins, np.float32)
        self.decay = config.smoothing ** (30 / fps)

    def at(self, samples, seconds):
        center = round(seconds * SAMPLE_RATE)
        start = center - FFT_SIZE // 2
        window = np.zeros((FFT_SIZE, 2), np.float32)
        left, right = max(0, start), min(len(samples), start + FFT_SIZE)
        if right > left:
            window[left - start:right - start] = samples[left:right]
        # Average channel power, not waveforms: anti-phase stereo must not cancel.
        transform = np.fft.rfft(window * self.window[:, None], axis=0)
        power = np.mean(np.abs(transform) ** 2, axis=1)
        amplitudes = np.sqrt(power) * 2 / self.window.sum()
        values = np.array([np.max(amplitudes[band]) if len(band) else np.interp(freq, self.frequencies, amplitudes)
                           for band, freq in zip(self.bands, self.centers)]) * self.config.gain
        if self.config.scale == "log":
            target = np.clip((20 * np.log10(np.maximum(values, 1e-9)) + 65) / 65, 0, 1)
        else:
            exponent = {"lin": 1, "sqrt": 0.5, "cbrt": 1 / 3}[self.config.scale]
            target = np.clip(values * 3, 0, 1) ** exponent
        # Fast attack and time-based release preserve transients at every frame rate.
        self.levels = np.where(target > self.levels, target, self.decay * self.levels + (1 - self.decay) * target)
        return self.levels


def palette(colors, count):
    stops = np.array([rgb(color) for color in colors.split("|")], dtype=float)
    return np.stack([np.interp(np.linspace(0, len(stops) - 1, count), np.arange(len(stops)), stops[:, c])
                     for c in range(3)], axis=1).astype(np.uint8)


def draw_visualizer(frame, config, levels, position):
    h, w = frame.shape[:2]
    scale = min(1, w / config.width, h / config.height)
    vw, vh = max(32, round(config.width * scale)), max(32, round(config.height * scale))
    fitted = config.model_copy(update={"width": vw, "height": vh})
    x, y = position(fitted, w, h)
    x, y = min(max(0, x), w - vw), min(max(0, y), h - vh)
    ink = np.zeros((vh, vw, 3), np.uint8)
    colors = palette(config.colors, len(levels))
    points = []
    circular = config.kind == "circular"
    if circular:
        # Mirror low-to-high bands around the circle for a balanced radial spectrum.
        order = np.concatenate([np.arange(0, len(levels), 2), np.arange(1, len(levels), 2)[::-1]])
        levels, colors = levels[order], colors[order]
        radius = min(vw, vh) * config.radius
        extent = min(vw, vh) * 0.47 - radius
        thickness = max(1, round(2 * math.pi * radius / len(levels) * config.bar_width))
        cv2.circle(ink, (vw // 2, vh // 2), round(radius - thickness * 1.6), tuple(int(c * .5) for c in colors[0]), 1, cv2.LINE_AA)
    else:
        length = vh if config.kind == "vertical" else vw
        thickness = max(1, round(length / len(levels) * config.bar_width))
    for i, (level, color) in enumerate(zip(levels, colors)):
        color = tuple(int(c) for c in color)
        if circular:
            angle = i / len(levels) * math.tau - math.pi / 2
            direction = np.array([math.cos(angle), math.sin(angle)])
            origin = np.array([vw / 2, vh / 2])
            a = origin + direction * radius
            b = origin + direction * (radius + max(1, level * extent))
        elif config.kind == "horizontal":
            a = np.array([(i + .5) * vw / len(levels), vh * .92])
            b = a - [0, max(1, level * vh * .82)]
        else:
            a = np.array([vw * .08, (i + .5) * vh / len(levels)])
            b = a + [max(1, level * vw * .82), 0]
        a, b = tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int))
        points.append(b)
        if config.mode == "bar":
            cv2.line(ink, a, b, color, thickness, cv2.LINE_AA)
            cv2.circle(ink, b, max(1, thickness // 2), color, -1, cv2.LINE_AA)
        elif config.mode == "dot":
            cv2.circle(ink, b, max(1, thickness // 2), color, -1, cv2.LINE_AA)
        elif i:
            cv2.line(ink, points[-2], b, color, max(1, thickness // 2), cv2.LINE_AA)
    if config.mode == "line" and circular:
        cv2.line(ink, points[-1], points[0], tuple(int(c) for c in colors[0]), max(1, thickness // 2), cv2.LINE_AA)
    if config.glow:
        halo = cv2.GaussianBlur(ink, (0, 0), max(1, min(vw, vh) / 100))
        ink = cv2.addWeighted(ink, 1, halo, config.glow, 0)
    roi = frame[y:y + vh, x:x + vw]
    base = roi.astype(np.float32) * (1 - config.background_opacity)
    # Screen blend keeps the background visible and the spectrum edges clean.
    roi[:] = np.clip(255 - (255 - base) * (1 - ink.astype(np.float32) * config.opacity / 255), 0, 255).astype(np.uint8)


def generated_background(config, width, height, seconds):
    # Animate at low resolution; expensive per-pixel work is independent of export size.
    y, x = np.mgrid[0:90, 0:160].astype(np.float32)
    x, y = x / 160, y / 90
    speed = {"aurora": .22, "nebula": .12, "gradient": .08, "plasma": .4}[config.generated_style]
    t = seconds * speed
    a, b, c = (np.array(rgb(value), dtype=np.float32) for value in (config.color_a, config.color_b, config.color_c))
    ribbon = np.exp(-((y - .45 - .18 * np.sin(x * 5 + t)) / .18) ** 2) * .24
    wash = (.5 + .5 * np.sin(x * 3 - y * 2 + t)) * .12
    frame = a + ribbon[..., None] * (b - a) + wash[..., None] * (c - a)
    if config.blur > 0:
        frame = cv2.GaussianBlur(frame, (0, 0), max(.1, config.blur / 12))
    return cv2.resize(np.clip(frame, 0, 255).astype(np.uint8), (width, height), interpolation=cv2.INTER_LINEAR)


def prepare_background(builder, request, folder, duration):
    rc = request.render_config
    clips = []
    for index, ref in enumerate(request.background.media_refs):
        clip = folder / f"background_{index}.mp4"
        source = Path(ref.resolve(Path(builder.config.media_root)))
        rate = request.background.playback_rate
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-an", "-t", str(duration),
                        "-vf", f"setpts=(PTS-STARTPTS)/{rate},scale={rc.viewport_w}:{rc.viewport_h}:force_original_aspect_ratio=increase,crop={rc.viewport_w}:{rc.viewport_h},setsar=1,fps={rc.fps}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)],
                       check=True, capture_output=True)
        clips.append(clip)
    manifest = folder / "clips.txt"
    manifest.write_text("\n".join("file '" + p.as_posix().replace("'", "'\\''") + "'" for p in clips), encoding="utf-8")
    return manifest


def compose_frame(builder, request, seconds, levels, background_frame=None):
    rc = request.render_config
    frame = (generated_background(request.background, rc.viewport_w, rc.viewport_h, seconds)
             if background_frame is None else background_frame.copy())
    for viz, energy in zip((v for v in request.visualizers if v.enabled), levels):
        draw_visualizer(frame, viz, energy, builder._overlay_position)
    return frame


def render_audio_video(builder, request, progress=None):
    from mn_contracts import common as common, ocr
    import uuid
    progress = progress or (lambda value, stage: None)
    rc = request.render_config
    width, height, fps = rc.viewport_w, rc.viewport_h, rc.fps
    audio = Path(request.audio_ref.resolve(Path(builder.config.media_root)))
    run_id = request.run_id or f"audio_video_{uuid.uuid4().hex[:12]}"
    output_root = Path(builder.config.media_root) / "outputs" / "audio_video" / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / builder._safe_output_name(request.output_name)
    progress(1, "Decoding audio")
    with tempfile.TemporaryDirectory(prefix="spectrum_", dir=output_root) as temp:
        temp = Path(temp)
        pcm = temp / "audio.f32"
        decode = ["ffmpeg", "-v", "error", "-y", "-i", str(audio)]
        if request.preview_seconds:
            decode += ["-t", str(request.preview_seconds)]
        subprocess.run(decode + ["-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", str(pcm)], check=True, capture_output=True)
        if pcm.stat().st_size == 0:
            raise ValueError("The uploaded file contains no decodable audio")
        samples = np.memmap(pcm, dtype=np.float32, mode="r").reshape(-1, 2)
        duration = len(samples) / SAMPLE_RATE
        decoder = None
        encoder = None
        try:
            if request.background.mode == "media":
                progress(3, "Preparing background clips")
                manifest = prepare_background(builder, request, temp, duration)
                decoder = subprocess.Popen(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(manifest),
                                            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            spectra = [(viz, Spectrum(viz, fps)) for viz in request.visualizers if viz.enabled]
            frames = math.ceil(duration * fps)
            encoded = temp / "result.mp4"
            command = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
                       "-r", str(fps), "-i", "pipe:0", "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration),
                       *builder._video_encoder_args(rc), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", rc.audio_bitrate,
                       "-movflags", "+faststart", str(encoded)]
            with (temp / "encoder.log").open("w+b") as errors:
                encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors, stdout=subprocess.DEVNULL)
                try:
                    for index in range(frames):
                        if decoder:
                            raw = decoder.stdout.read(width * height * 3)
                            if len(raw) != width * height * 3:
                                raise RuntimeError("Background decoder ended unexpectedly")
                            frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3).copy()
                        else:
                            frame = None
                        levels = [spectrum.at(samples, index / fps) for viz, spectrum in spectra]
                        frame = compose_frame(builder, request, index / fps, levels, frame)
                        encoder.stdin.write(frame.tobytes())
                        if index % max(1, fps // 2) == 0:
                            progress(5 + 90 * index / frames, "Rendering spectrum (" + rc.vcodec + ")")
                    encoder.stdin.close()
                    progress(97, "Finalizing MP4")
                    encoder.wait(timeout=120)
                    if encoder.returncode:
                        raise RuntimeError("Video encoder failed")
                except (BrokenPipeError, RuntimeError) as exc:
                    errors.seek(0)
                    detail = errors.read().decode("utf-8", errors="replace")[-4000:]
                    raise RuntimeError(f"{exc}: {detail}") from exc
            encoded.replace(output)
        finally:
            for process in (encoder, decoder):
                if process:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                    for stream in (process.stdin, process.stdout):
                        if stream:
                            try:
                                stream.close()
                            except OSError:
                                pass
            samples._mmap.close()
    progress(100, "Complete")
    return common.build_media_Ref(namespace=ocr.MediaNamespace.OUTPUTS, path=output, media_root=builder.config.media_root)
