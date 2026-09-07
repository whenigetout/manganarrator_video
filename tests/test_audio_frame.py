import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess

import cv2
import numpy as np

from app.audio_frame import render_preview_frame, preview_png, levels_at
from app.audio_spectrum import compose_frame
from app.chapter_video_builder import ChapterVideoBuilder
from app.models.domain import AudioVideoRequest, AudioVideoBackgroundConfig


class FramePreviewTests(unittest.TestCase):
    def test_exact_export_frame_and_determinism(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "outputs").mkdir()
            audio = root / "outputs" / "test.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=700:duration=1",
                            str(audio)], check=True)
            builder = ChapterVideoBuilder(SimpleNamespace(media_root=str(root)))
            request = AudioVideoRequest.model_validate({
                "audio_ref": {"namespace":"outputs","path":"test.wav"},
                "render_config":{"viewport_w":640,"viewport_h":360,"fps":24,"vcodec":"libx264"},
                "visualizers":[{"width":280,"height":280,"position":"center","smoothing":.98,"scale":"log"}]})
            captured = []
            def record(*args, **kwargs):
                frame = compose_frame(*args, **kwargs)
                if args[2] == .5:
                    captured.append(frame.copy())
                return frame
            with patch("app.audio_spectrum.compose_frame", side_effect=record):
                builder.build_audio_video(request)
            live, timestamp = render_preview_frame(builder, request, .5)
            self.assertEqual(timestamp, .5)
            np.testing.assert_array_equal(live, captured[0])
            levels_at.cache_clear()
            repeated, _ = render_preview_frame(builder, request, .5)
            np.testing.assert_array_equal(live, repeated)
            png, _ = preview_png(builder, request, .5)
            decoded = cv2.cvtColor(cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            np.testing.assert_array_equal(live, decoded)
            for change in ({"colors":"#ff0000"}, {"kind":"horizontal"}, {"enabled":False},
                           {"width":150}, {"position":"top_left"}, {"scale":"lin"}):
                changed = request.model_copy(deep=True)
                changed.visualizers[0] = changed.visualizers[0].model_copy(update=change)
                updated, _ = render_preview_frame(builder, changed, .5)
                self.assertFalse(np.array_equal(live, updated), change)

            clip = root / "outputs" / "background.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=15:d=0.35",
                            "-c:v", "libx264", str(clip)], check=True)
            request.background = AudioVideoBackgroundConfig.model_validate({"mode": "media", "media_refs": [{"namespace": "outputs", "path": "background.mp4"}]})
            captured.clear()
            with patch("app.audio_spectrum.compose_frame", side_effect=record):
                builder.build_audio_video(request)
            media_frame, _ = render_preview_frame(builder, request, .5)
            np.testing.assert_array_equal(media_frame, captured[0])

    def test_demo_and_export_dimensions(self):
        builder = ChapterVideoBuilder(SimpleNamespace(media_root="."))
        request = AudioVideoRequest.model_validate({
            "audio_ref":{"namespace":"outputs","path":"not-used.wav"},
            "render_config":{"viewport_w":640,"viewport_h":360}})
        frame, _ = render_preview_frame(builder, request, 2, demo=True)
        self.assertEqual(frame.shape, (360,640,3))
        request.render_config.viewport_w = 1280
        request.render_config.viewport_h = 720
        larger, _ = render_preview_frame(builder, request, 2, demo=True)
        self.assertEqual(larger.shape, (720,1280,3))


if __name__ == "__main__":
    unittest.main()
