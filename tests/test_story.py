import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import wave
from PIL import Image
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from mn_contracts.story import StoryProject, ScriptSegment, VisualShot
from app.story.importer import import_story
from app.story.store import StoryStore, Conflict, probe_duration
from app.story.timeline import compile_timeline
from app.story.render import render_story
from app.story.api import install_story
from jobs import jobs_db

DEMO = Path(__file__).parents[1] / "fixtures/story-demo.md"


def wav(seconds):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
        out.writeframes(b'\x10\x00' * round(16000 * seconds))
    buf.seek(0)
    return UploadFile(filename="voice.wav", file=buf)


def png():
    buf = io.BytesIO()
    Image.new("RGB", (640, 400), "#385c7f").save(buf, format="PNG")
    buf.seek(0)
    return UploadFile(filename="image.png", file=buf)


class StoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StoryStore(Path(self.temp.name) / "stories")
        self.project = self.store.create(import_story(DEMO.read_text(), "markdown"))

    def speech(self, line="line-one", seconds=.4):
        self.project, asset = self.store.upload(self.project.id, wav(seconds), "audio", self.project.revision, line)
        return asset

    def image(self):
        self.project, asset = self.store.upload(self.project.id, png(), "image", self.project.revision)
        return asset

    def save(self, project):
        self.project = self.store.save(project.id, project, project.revision)

    def complete(self):
        for line in ("line-one", "line-two", "line-three"):
            self.speech(line)
        image = self.image()
        p = self.project.model_copy(deep=True)
        for scene in p.arcs[0].chapters[0].scenes:
            scene.shots = [VisualShot(id="shot-"+scene.id, image_asset_id=image.id, motion="slow_zoom", fade_in=.05, fade_out=.05)]
        self.save(p)

    def test_markdown_import_stable_ids_and_speaker_split(self):
        self.assertEqual(self.project.arcs[0].chapters[0].scenes[0].segments[1].character_id, "KEEPER")
        self.assertEqual(len(self.project.characters), 2)
        self.assertIn("[line-one]", self.project.arcs[0].chapters[0].scenes[0].canonical_text)

    def test_unstructured_text_rejected_not_silently_lost(self):
        for text in ("# A novel\nA paragraph", DEMO.read_text()+"\nOOC: change the ending", DEMO.read_text().replace("[line-two]", "[line-one]")):
            with self.assertRaises(ValueError):
                import_story(text, "markdown")

    def test_schema_rejects_bad_references_and_nonfinite_timing(self):
        d = self.project.model_dump()
        d["arcs"][0]["chapters"][0]["scenes"][0]["segments"][0]["character_id"] = "unknown"
        with self.assertRaises(ValueError): StoryProject.model_validate(d)
        with self.assertRaises(ValueError): VisualShot(id="shot", timing="manual", duration=float("nan"))
        with self.assertRaises(ValueError): ScriptSegment(id="silence", kind="silence", silence_seconds=0)
        with self.assertRaises(ValueError): self.store.read("../outside")

    def test_real_duration_replaces_only_one_take(self):
        first = self.speech(seconds=.4)
        self.speech("line-two", .6)
        second = self.speech(seconds=.8)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(self.project.assets), 3)
        line = compile_timeline(self.project, "chapter-one")["audio"]
        self.assertAlmostEqual(line[0]["duration"], .8, places=3)
        self.assertAlmostEqual(line[1]["start"], .8, places=3)
        self.assertAlmostEqual(line[1]["duration"], .6, places=3)

    def test_missing_and_stale_audio_blocks_render(self):
        self.complete()
        self.assertTrue(compile_timeline(self.project)["ready"])
        p = self.project.model_copy(deep=True)
        p.arcs[0].chapters[0].scenes[0].segments[0].text = "A new reading."
        self.save(p)
        t = compile_timeline(self.project)
        self.assertFalse(t["ready"])
        self.assertTrue(any("stale audio" in x for x in t["conflicts"]))
        with self.assertRaises(ValueError): render_story(self.store, self.project, Path(self.temp.name)/"blocked")

    def test_character_voice_invalidates_take(self):
        self.complete()
        p = self.project.model_copy(deep=True)
        p.characters[0].voice = "different-voice"
        self.save(p)
        self.assertTrue(any("line-two: stale" in x for x in compile_timeline(self.project)["conflicts"]))

    def test_manual_placements_preserved_on_regeneration(self):
        self.complete()
        p = self.project.model_copy(deep=True)
        shot = p.arcs[0].chapters[0].scenes[0].shots[0]
        shot.timing = "manual"; shot.duration = 1.1
        self.save(p)
        self.assertTrue(compile_timeline(self.project)["ready"])
        self.speech(seconds=.2)
        shot = self.project.arcs[0].chapters[0].scenes[0].shots[0]
        self.assertEqual(shot.duration, 1.1)
        self.assertFalse(compile_timeline(self.project)["ready"])

    def test_locks_canon_and_optimistic_revisions(self):
        p = self.project.model_copy(deep=True)
        p.arcs[0].chapters[0].scenes[0].canonical_text = "overwrite"
        with self.assertRaises(ValueError): self.save(p)
        p = self.project.model_copy(deep=True)
        p.arcs[0].chapters[0].scenes[0].locked = True
        self.save(p)
        stale = self.project.model_copy(deep=True)
        with self.assertRaises(Conflict): self.speech()
        p = self.project.model_copy(deep=True)
        p.arcs[0].chapters[0].scenes[0].segments[0].text = "changed"
        with self.assertRaises(Conflict): self.save(p)
        p = self.project.model_copy(deep=True)
        p.title = "New title"
        self.save(p)
        with self.assertRaises(Conflict): self.save(stale)

    def test_history_restore_and_duplicate_preserve_assets(self):
        self.speech()
        p = self.project.model_copy(deep=True)
        p.title = "Changed title"; self.save(p)
        restored = self.store.restore(p.id, 0, self.project.revision)
        self.assertEqual(restored.title, "The Lantern Road")
        self.assertEqual(len(restored.assets), 1)
        copy = self.store.duplicate(restored.id, restored.revision)
        self.assertNotEqual(copy.id, restored.id)
        self.assertTrue(self.store.asset_path(copy, copy.assets[0]).is_file())

    def test_scope_selection_independent_of_other_missing_scenes(self):
        self.complete()
        p = self.project.model_copy(deep=True)
        p.arcs[0].chapters[0].scenes[1].segments[0].audio_asset_id = None
        self.save(p)
        self.assertTrue(compile_timeline(self.project, scene_id="gate")["ready"])
        self.assertFalse(compile_timeline(self.project)["ready"])

    def test_actual_ffmpeg_export_duration_and_manifest(self):
        self.complete()
        out = Path(self.temp.name)/"render"
        manifest = render_story(self.store, self.project, out, width=320, height=180, fps=24)
        data = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(out/'episode.mp4')]))
        self.assertEqual({s['codec_type'] for s in data['streams']}, {'audio','video'})
        self.assertAlmostEqual(float(data['format']['duration']), 1.5, delta=.05)
        self.assertEqual(manifest['timeline']['timing_basis'], 'measured_audio_plus_explicit_silence')
        self.assertTrue((out/'manifest.json').is_file())
        self.assertFalse((out/'tmp').exists())

    def test_api_import_save_upload_schema_and_render_conflict(self):
        app = FastAPI()
        with patch.dict('os.environ', {'STORY_STUDIO_ROOT': str(Path(self.temp.name)/'api')}):
            install_story(app, SimpleNamespace(config=SimpleNamespace(media_root=self.temp.name)))
        with TestClient(app) as client:
            self.assertEqual(client.get('/video/story/schema').status_code, 200)
            p = client.post('/video/story/import', json={'format':'markdown', 'content':DEMO.read_text()}).json()
            base = '/video/story/projects/'+p['id']
            bad = dict(p, title='New title')
            self.assertEqual(client.put(base,json=bad).status_code, 200)
            self.assertEqual(client.put(base,json=bad).status_code, 409)
            p = client.get(base).json()
            take = wav(.5)
            response = client.post(base+'/assets', data={'kind':'audio','revision':p['revision'],'segment_id':'line-one'}, files={'file':('take.wav',take.file,'audio/wav')})
            self.assertEqual(response.status_code,200,response.text)
            p = response.json()['project']
            asset = response.json()['asset']
            self.assertEqual(client.get(base+'/assets/'+asset['id']).status_code,200)
            self.assertEqual(client.post(base+'/render',json={'revision':p['revision'],'chapter_id':'chapter-one'}).status_code,422)
            self.assertEqual(len(client.get('/video/story/projects').json()),1)

if __name__ == '__main__':
    unittest.main()
