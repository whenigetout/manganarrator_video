import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from app.publishing.youtube import YouTube, confirmed_offset, check_response
from app.publishing.models import PublishingError
from support_publishing import Fixture


class FakeOAuth:
    def __init__(self): self.refreshes=0
    def verify(self,profile): pass
    def credentials(self,profile,force=False):
        self.refreshes+=int(force)
        return SimpleNamespace(token="fake-token")


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.oauth=FakeOAuth();self.path=self.f.root/"video.mp4";self.path.write_bytes(b"abcdefgh")
        self.run={"id":"run1","profile":{"language":"en"},"metadata":{"title":"Test","description":"","tags":[]},
                  "review":{"category":"10","privacy":"private","made_for_kids":False,"contains_synthetic_media":False}}
    def tearDown(self): self.f.close()
    def checkpoint(self,values): self.run.update(values)
    def test_chunk_ranges_resume_and_refresh(self):
        requests=[]
        def transport(request):
            requests.append(request)
            if len(requests)==1: return httpx.Response(401)
            if request.method=="POST": return httpx.Response(200,headers={"Location":"https://www.googleapis.com/upload/session"})
            range_=request.headers.get("Content-Range")
            if range_=="bytes */8": return httpx.Response(308,headers={"Range":"bytes=0-3"})
            self.assertEqual(range_,"bytes 4-7/8");self.assertEqual(request.content,b"efgh")
            return httpx.Response(201,json={"id":"abcdefghijk"})
        youtube=YouTube(self.oauth,self.f.settings,httpx.MockTransport(transport))
        with patch("app.publishing.youtube.CHUNK_SIZE",4): result=youtube.upload(self.run,self.path,self.checkpoint)
        self.assertEqual(result["id"],"abcdefghijk");self.assertEqual(self.oauth.refreshes,1)
        self.assertEqual(self.run["upload_bytes"],4)
    def test_lost_completion_queries_same_session_without_new_upload(self):
        self.f.settings.set_secret("upload:run1","https://www.googleapis.com/upload/session")
        calls=[]
        def transport(request):
            calls.append(request)
            if len(calls)==1: return httpx.Response(308)
            raise httpx.ReadTimeout("secret-session",request=request)
        youtube=YouTube(self.oauth,self.f.settings,httpx.MockTransport(transport))
        with self.assertRaises(PublishingError) as error: youtube.upload(self.run,self.path,self.checkpoint)
        self.assertEqual(error.exception.kind,"retry_wait")
        recovered=[]
        def complete(request):
            recovered.append(request)
            return httpx.Response(200,json={"id":"abcdefghijk"})
        youtube=YouTube(self.oauth,self.f.settings,httpx.MockTransport(complete))
        self.assertEqual(youtube.upload(self.run,self.path,self.checkpoint)["id"],"abcdefghijk")
        self.assertEqual(len(recovered),1);self.assertEqual(recovered[0].headers["Content-Range"],"bytes */8")
    def test_expired_and_missing_session_never_auto_restart(self):
        self.f.settings.set_secret("upload:run1","https://www.googleapis.com/upload/session")
        requests=[]
        def expired(request): requests.append(request);return httpx.Response(404)
        with self.assertRaises(PublishingError) as error: YouTube(self.oauth,self.f.settings,httpx.MockTransport(expired)).upload(self.run,self.path,self.checkpoint)
        self.assertEqual(error.exception.kind,"needs_attention");self.assertEqual(len(requests),1)
        self.f.settings.delete_secret("upload:run1");self.run["session_created"]=True
        with self.assertRaises(PublishingError): YouTube(self.oauth,self.f.settings).upload(self.run,self.path,self.checkpoint)
    def test_retry_classification_and_offsets(self):
        self.assertEqual(confirmed_offset(httpx.Response(308),8),0)
        with self.assertRaises(PublishingError): confirmed_offset(httpx.Response(308,headers={"Range":"bytes=0-8"}),8)
        with self.assertRaises(PublishingError) as error: check_response(httpx.Response(503,headers={"Retry-After":"90"}))
        self.assertEqual(error.exception.delay,90)
        with self.assertRaises(PublishingError) as error: check_response(httpx.Response(403,json={"error":{"errors":[{"reason":"quotaExceeded"}]}}))
        self.assertEqual(error.exception.kind,"failed")
