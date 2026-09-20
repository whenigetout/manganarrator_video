import unittest
import json
import subprocess
from unittest.mock import patch, Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.publishing.api import install_publishing
from app.publishing.models import Review, PublishingError
from app.publishing.store import Conflict
from app.publishing.workflow import Workflow, media_path
from support_publishing import Fixture


class WorkflowTests(unittest.TestCase):
    def setUp(self): self.f=Fixture()
    def tearDown(self): self.f.close()
    def ready(self):
        run=self.f.rendered(self.f.run());self.f.workflow.step(run["id"]);return self.f.store.run(run["id"])
    def review(self,run): return Review(revision=run["revision"],metadata=run["metadata"],made_for_kids=False,contains_synthetic_media=False)
    def test_render_to_review_no_automatic_upload(self):
        run=self.ready()
        self.assertEqual(run["state"],"awaiting_review");self.assertIn("No metadata provider",run["metadata_error"])
        self.f.workflow.step(run["id"])
        self.assertIsNone(self.f.store.run(run["id"])["video_id"])
    def test_approval_revision_and_artifact_integrity(self):
        run=self.ready();review=self.review(run)
        updated=self.f.workflow.review(run["id"],review)
        with self.assertRaises(Conflict): self.f.workflow.review(run["id"],review,True)
        self.f.workflow.review(run["id"],self.review(updated),True)
        path=media_path(self.f.builder,run["artifact"]["ref"],True);path.write_bytes(b"changed")
        self.f.workflow.step(run["id"])
        self.assertEqual(self.f.store.run(run["id"])["state"],"needs_attention")
    def test_success_tracks_upload_then_processing(self):
        run=self.ready();self.f.workflow.review(run["id"],self.review(run),True)
        youtube=Mock();youtube.upload.return_value={"id":"abcdefghijk","status":{"privacyStatus":"private"}};youtube.processing.return_value=(True,"private")
        self.f.workflow.youtube=youtube;self.f.workflow.step(run["id"])
        self.assertEqual(self.f.store.run(run["id"])["state"],"youtube_processing")
        self.f.workflow.step(run["id"])
        final=self.f.store.run(run["id"])
        self.assertEqual(final["state"],"completed");self.assertEqual(final["video_url"],"https://www.youtube.com/watch?v=abcdefghijk")
        with self.assertRaises(Conflict): self.f.workflow.retry(run["id"],True)
    def test_restart_recovers_render_and_only_one_worker(self):
        run=self.f.run();self.f.store.change(run["id"],{"state":"rendering"})
        with patch.object(self.f.workflow,"loop"):
            self.f.workflow.start()
            self.assertEqual(self.f.store.run(run["id"])["state"],"queued")
            second=Workflow(self.f.builder,self.f.settings,self.f.store,None)
            from filelock import Timeout
            with self.assertRaises(Timeout): second.start()
            self.f.workflow.stop()
    def test_profile_snapshot_does_not_drift(self):
        run=self.f.run();self.f.store.put("profiles",{**self.f.profile,"name":"Changed","privacy":"unlisted"},self.f.profile["id"])
        self.assertEqual(self.f.store.run(run["id"])["profile"]["privacy"],"private")
    def test_completed_upload_survives_secret_cleanup_failure(self):
        run=self.ready();self.f.workflow.review(run["id"],self.review(run),True)
        youtube=Mock();youtube.upload.return_value={"id":"abcdefghijk"};youtube.processing.return_value=(True,"private")
        self.f.workflow.youtube=youtube
        with patch.object(self.f.settings,"delete_secret",side_effect=RuntimeError("vault unavailable")):
            self.f.workflow.step(run["id"])
        self.assertEqual(self.f.store.run(run["id"])["state"],"youtube_processing")
        self.f.store.change(run["id"],{"state":"uploading"})
        self.f.workflow.step(run["id"]);self.f.workflow.step(run["id"])
        self.assertEqual(self.f.store.run(run["id"])["state"],"completed")
        self.assertEqual(youtube.upload.call_count,1)
    def test_failed_upload_validation_can_return_to_review(self):
        run=self.ready();self.f.workflow.review(run["id"],self.review(run),True)
        self.f.store.change(run["id"],{"state":"failed"})
        edited=self.f.workflow.reopen_review(run["id"])
        self.assertEqual(edited["state"],"awaiting_review");self.assertIsNone(edited["approved_revision"])
        self.f.store.change(run["id"],{"state":"failed","session_created":True})
        with self.assertRaises(Conflict): self.f.workflow.reopen_review(run["id"])
    def test_actual_mp3_render_reaches_review_and_keeps_artifact_on_regenerate(self):
        from app.chapter_video_builder import ChapterVideoBuilder
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","sine=duration=0.4",str(self.f.source)],check=True)
        mp3=self.f.source.with_suffix(".mp3")
        subprocess.run(["ffmpeg","-v","error","-y","-i",str(self.f.source),str(mp3)],check=True)
        self.f.request.audio_ref={"namespace":"outputs","path":"audio_video_uploads/test.mp3"}
        self.f.request.source_name="My recording.mp3"
        self.f.request.config={"render_config":{"viewport_w":320,"viewport_h":180,"fps":10,"vcodec":"libx264"}}
        self.f.workflow.builder=ChapterVideoBuilder(self.f.builder.config)
        run=self.f.run();self.f.workflow.step(run["id"]);self.f.workflow.step(run["id"])
        completed=self.f.store.run(run["id"])
        self.assertEqual(completed["state"],"awaiting_review")
        path=media_path(self.f.builder,completed["artifact"]["ref"],True)
        probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(path)],capture_output=True,text=True,check=True)
        self.assertAlmostEqual(float(json.loads(probe.stdout)["format"]["duration"]),.4,delta=.12)
        before=path.stat().st_mtime_ns
        self.f.workflow.regenerate(run["id"]);self.f.workflow.step(run["id"])
        self.assertEqual(path.stat().st_mtime_ns,before)
    def test_api_auth_origin_and_review_gate(self):
        app=FastAPI();install_publishing(app,self.f.builder,self.f.settings)
        with TestClient(app) as client:
            prefix="/video/publishing"
            self.assertEqual(client.get(prefix+"/profiles").status_code,401)
            headers={"Authorization":"Bearer "+self.f.settings.owner_key(),"X-Publishing-Client":"studio"}
            self.assertEqual(client.get(prefix+"/profiles",headers={**headers,"Origin":"https://evil.test"}).status_code,403)
            self.assertEqual(client.post(prefix+"/session",headers=headers).status_code,200)
            self.assertEqual(client.get(prefix+"/profiles",headers={"X-Publishing-Client":"studio"}).status_code,200)
            run=self.f.run()
            review={"revision":1,"metadata":{"title":"Test"},"made_for_kids":False,"contains_synthetic_media":False}
            self.assertEqual(client.post(prefix+f"/runs/{run['id']}/upload",headers=headers,json=review).status_code,409)
