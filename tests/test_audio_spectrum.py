import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from app.audio_spectrum import SAMPLE_RATE, Spectrum, draw_visualizer, generated_background
from app.models.domain import AudioVisualizerConfig, AudioVideoRequest, RenderConfig
from app.chapter_video_builder import ChapterVideoBuilder
from mn_contracts.ocr import MediaRef


class SpectrumTests(unittest.TestCase):
    def test_frequency_and_stereo_phase(self):
        config = AudioVisualizerConfig(scale="log", smoothing=0)
        t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
        tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32) * .5
        samples = np.stack([tone, -tone], axis=1)
        spectrum = Spectrum(config, 30)
        levels = spectrum.at(samples, .5)
        peak = spectrum.centers[np.argmax(levels)]
        self.assertLess(abs(math.log(peak / 1000)), .16)
        self.assertGreater(levels.max(), .7)
        self.assertEqual(spectrum.at(np.zeros_like(samples), .5).max(), 0)

    def test_release_and_all_layouts(self):
        config = AudioVisualizerConfig(smoothing=.7, scale="log")
        spectrum = Spectrum(config, 30)
        spectrum.levels[:] = 1
        level = spectrum.at(np.zeros((SAMPLE_RATE, 2), np.float32), .5)
        self.assertTrue(np.allclose(level, .7))
        for kind in ("circular", "horizontal", "vertical"):
            for mode in ("bar", "line", "dot"):
                viz = AudioVisualizerConfig(kind=kind, mode=mode, width=300, height=300)
                frame = np.zeros((360, 640, 3), np.uint8)
                draw_visualizer(frame, viz, np.linspace(0, 1, 64), lambda *args: (300, 80))
                self.assertGreater(np.count_nonzero(frame), 100)

    def test_invalid_config(self):
        base = {"audio_ref": {"namespace": "outputs", "path": "test.wav"}}
        for change in ({"run_id": "../escape"}, {"render_config": {"viewport_w": 721}},
                       {"visualizers": [{"colors": "invalid"}]}, {"background": {"mode": "media"}}):
            with self.assertRaises(ValueError):
                AudioVideoRequest.model_validate({**base, **change})

    def test_mixed_background_clips_loop_and_trim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "outputs").mkdir()
            wav = root / "outputs" / "tone.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1.25", str(wav)], check=True)
            for name, size, rate in (("red", "240x180", 15), ("blue", "180x240", 30)):
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color={name}:s={size}:r={rate}:d=0.3",
                                "-c:v", "libx264", str(root / "outputs" / f"{name}.mp4")], check=True)
            request = AudioVideoRequest.model_validate({"audio_ref": {"namespace": "outputs", "path": "tone.wav"},
                "render_config": {"viewport_w": 640, "viewport_h": 360, "fps": 24, "vcodec": "libx264"},
                "background": {"mode": "media", "media_refs": [{"namespace": "outputs", "path": f"{name}.mp4"} for name in ("red", "blue")]},
                "visualizers": []})
            result = ChapterVideoBuilder(SimpleNamespace(media_root=str(root))).build_audio_video(request)
            capture = cv2.VideoCapture(str(result.resolve(root)))
            colors = []
            for time in (100, 450, 800):
                capture.set(cv2.CAP_PROP_POS_MSEC, time)
                ok, frame = capture.read()
                self.assertTrue(ok)
                colors.append(frame[180, 320])
            capture.release()
            self.assertGreater(int(colors[0][2]), 200)
            self.assertGreater(int(colors[1][0]), 200)
            self.assertGreater(int(colors[2][2]), 200)

    def test_mp3_wav_export_and_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "outputs").mkdir()
            wav = root / "outputs" / "tone.wav"
            mp3 = wav.with_suffix(".mp3")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.25", str(wav)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), str(mp3)], check=True)
            builder = ChapterVideoBuilder(SimpleNamespace(media_root=str(root)))
            for audio in (wav, mp3):
                request = AudioVideoRequest(audio_ref=MediaRef(namespace="outputs", path=audio.name),
                    render_config=RenderConfig(viewport_w=640, viewport_h=360, fps=24, vcodec="libx264"),
                    visualizers=[AudioVisualizerConfig(width=260, height=260, position="center", scale="log")])
                progress = []
                result = builder.build_audio_video(request, lambda value, stage: progress.append(value))
                output = Path(result.resolve(root))
                probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]))
                self.assertEqual({s["codec_type"] for s in probe["streams"]}, {"video", "audio"})
                self.assertLess(abs(float(probe["format"]["duration"]) - 1.25), .08)
                self.assertEqual(progress[-1], 100)
                capture = cv2.VideoCapture(str(output))
                okay, first = capture.read()
                capture.set(cv2.CAP_PROP_POS_MSEC, 600)
                okay2, later = capture.read()
                capture.release()
                self.assertTrue(okay and okay2)
                self.assertGreater(float(first.std()), 2)
                self.assertGreater(float(np.abs(first.astype(float) - later).mean()), .01)


if __name__ == "__main__":
    unittest.main()
