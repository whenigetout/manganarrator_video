import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
import httpx
from google.auth.exceptions import RefreshError
from app.publishing.oauth import OAuth
from app.publishing.models import PublishingError
from app.publishing.youtube import YouTube
from app.publishing.api import valid_session, session_token, public_profile, public_run
from support_publishing import Fixture


class OAuthTests(unittest.TestCase):
    def setUp(self): self.f=Fixture();self.oauth=OAuth(self.f.settings,self.f.store)
    def tearDown(self): self.f.close()
    def test_grants_are_separate(self):
        self.f.settings.set_secret("grant:grant1",json.dumps({"token":"first"}))
        self.f.settings.set_secret("grant:grant2",json.dumps({"token":"second"}))
        def creds(info,scopes): return SimpleNamespace(valid=True,token=info["token"])
        with patch("app.publishing.oauth.Credentials.from_authorized_user_info",side_effect=creds):
            self.assertEqual(self.oauth.credentials({"credential_id":"grant1"}).token,"first")
            self.assertEqual(self.oauth.credentials({"credential_id":"grant2"}).token,"second")
        self.oauth.disconnect({"credential_id":"grant1"})
        self.assertIsNotNone(self.f.settings.get_secret("grant:grant2"))
    def test_invalid_grant_requires_reauthorization(self):
        self.f.settings.set_secret("grant:grant1","{}")
        credential=Mock(valid=False)
        credential.refresh.side_effect=RefreshError("invalid_grant secret")
        with patch("app.publishing.oauth.Credentials.from_authorized_user_info",return_value=credential):
            with self.assertRaises(PublishingError) as caught: self.oauth.credentials(self.f.profile)
        self.assertEqual(caught.exception.kind,"needs_reauth")
        self.assertNotIn("secret",str(caught.exception))
    def test_wrong_channel_blocked(self):
        with patch.object(self.oauth,"credentials",return_value=SimpleNamespace(token="fake")),patch.object(self.oauth,"channel",return_value={"id":"different"}):
            with self.assertRaises(PublishingError): self.oauth.verify(self.f.profile)
    def test_session_and_public_serializers(self):
        token=session_token("key")
        self.assertTrue(valid_session("key",token))
        self.assertFalse(valid_session("other",token))
        self.assertFalse(valid_session("key",session_token("key",now=1)))
        self.assertNotIn("credential_id",public_profile(self.f.profile,self.f.settings))
        self.assertNotIn("credential_id",public_run(self.f.run())["profile"])

    def test_global_client_completes_two_independent_profile_authorizations(self):
        first = self.f.store.put("profiles", {"name": "Music"})
        second = self.f.store.put("profiles", {"name": "Stories"})
        client_config = {"web": {"client_id": "shared-client", "client_secret": "dummy-client-secret"}}
        def flow_for(label):
            flow = Mock()
            flow.code_verifier = "verifier-" + label
            flow.authorization_url.return_value = ("https://accounts.google.com/authorize", "state-" + label)
            flow.credentials.token = "access-" + label
            flow.credentials.refresh_token = "refresh-" + label
            flow.credentials.to_json.return_value = json.dumps({"token": "access-" + label, "refresh_token": "refresh-" + label})
            return flow
        music, stories = flow_for("music"), flow_for("stories")
        def channel_response(url, params, headers, timeout):
            self.assertEqual(url, "https://www.googleapis.com/youtube/v3/channels")
            self.assertEqual(params, {"part": "id,snippet", "mine": "true"})
            label = headers["Authorization"].removeprefix("Bearer access-")
            return httpx.Response(200, json={"items": [{"id": "UC_" + label, "snippet": {"title": label.title(), "customUrl": "@" + label}}]})
        with patch.object(self.f.settings, "oauth_config", create=True, return_value=client_config), \
             patch("app.publishing.oauth.Flow.from_client_config", side_effect=[music, music, stories, stories]) as factory, \
             patch("app.publishing.oauth.httpx.get", side_effect=channel_response):
            self.oauth.begin(first["id"])
            a = self.oauth.finish("state-music", "code-music")
            self.oauth.begin(second["id"])
            b = self.oauth.finish("state-stories", "code-stories")
        self.assertTrue(all(call.args[0] == client_config for call in factory.call_args_list))
        self.assertNotEqual(a["credential_id"], b["credential_id"])
        self.assertEqual(a["channel_handle"], "@music")
        self.assertEqual(b["channel_id"], "UC_stories")
        self.assertEqual(a["connection_status"], "connected")
        self.assertEqual(json.loads(self.f.settings.get_secret("grant:" + b["credential_id"]))["refresh_token"], "refresh-stories")
        self.assertNotIn("access-music", json.dumps(public_profile(a, self.f.settings)))
        self.oauth.disconnect(a)
        self.assertEqual(public_profile(a, self.f.settings)["connection_status"], "disconnected")
        self.assertTrue(public_profile(b, self.f.settings)["connected"])

    def test_reconnect_preserves_binding_and_does_not_invent_a_handle(self):
        flow = Mock()
        flow.credentials.refresh_token = "new-refresh"
        flow.credentials.token = "new-access"
        flow.credentials.to_json.return_value = "new-grant"
        def finish(channel):
            self.f.store.save_state("reconnect", {"profile_id": self.f.profile["id"], "channel_id": "UC_test", "verifier": "pkce"})
            self.f.settings.set_secret("pkce", "verifier")
            with patch.object(self.f.settings, "oauth_config", create=True, return_value={}), \
                 patch("app.publishing.oauth.Flow.from_client_config", return_value=flow), \
                 patch.object(self.oauth, "channel", return_value=channel):
                return self.oauth.finish("reconnect", "new-code")
        with self.assertRaises(ValueError): finish({"id": "UC_wrong", "snippet": {"title": "Wrong channel"}})
        self.assertEqual(self.f.settings.get_secret("grant:grant1"), "fake")
        for snippet in ({"title": "Renamed", "customUrl": "legacyCustomURL"}, {"title": "Renamed"}):
            result = finish({"id": "UC_test", "snippet": snippet})
            self.assertEqual(result["credential_id"], "grant1")
            self.assertEqual(result["channel_name"], "Renamed")
            self.assertIsNone(result["channel_handle"])

    def test_revoked_grant_is_visible_as_reconnect_required(self):
        self.f.settings.set_secret("grant:grant1", "{}")
        credential = Mock(valid=False)
        credential.refresh.side_effect = RefreshError("invalid_grant")
        with patch("app.publishing.oauth.Credentials.from_authorized_user_info", return_value=credential):
            with self.assertRaises(PublishingError): self.oauth.credentials(self.f.profile)
        profile = public_profile(self.f.store.get("profiles", self.f.profile["id"]), self.f.settings)
        self.assertEqual(profile["connection_status"], "needs_reauth")
        self.assertFalse(profile["connected"])

    def test_upload_transport_uses_each_selected_profiles_grant(self):
        self.f.settings.set_secret("grant:a", json.dumps({"token": "access-a"}))
        self.f.settings.set_secret("grant:b", json.dumps({"token": "access-b"}))
        headers = []
        def transport(request):
            headers.append(request.headers["Authorization"])
            return httpx.Response(200, json={})
        youtube = YouTube(self.oauth, self.f.settings, httpx.MockTransport(transport))
        with patch("app.publishing.oauth.Credentials.from_authorized_user_info", side_effect=lambda info, scopes: SimpleNamespace(valid=True, token=info["token"])):
            youtube.request({"credential_id": "a"}, "POST", "https://www.googleapis.com/upload/youtube/v3/videos")
            youtube.request({"credential_id": "b"}, "POST", "https://www.googleapis.com/upload/youtube/v3/videos")
        self.assertEqual(headers, ["Bearer access-a", "Bearer access-b"])
