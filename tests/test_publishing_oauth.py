import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError
from app.publishing.oauth import OAuth, SCOPES, response_diagnostic
from app.publishing.models import PublishingError
from app.publishing.youtube import YouTube
from app.publishing.api import valid_session, session_token, public_profile, public_run, install_publishing
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
        music.authorization_url.assert_called_once_with(
            access_type="offline", prompt="select_account consent", include_granted_scopes="true")
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

    def test_channel_discovery_distinguishes_empty_and_ambiguous_results(self):
        channel = {"id": "UC_test", "snippet": {"title": "Music"}}
        for payload, message in (
            ({"items": []}, "0 channels"),
            ({}, "0 channels"),
            ({"items": [channel, {"id": "UC_other"}]}, "multiple channels"),
            ({"items": [channel], "nextPageToken": "more"}, "multiple channels"),
        ):
            with self.subTest(payload=payload), patch("app.publishing.oauth.httpx.get", return_value=httpx.Response(200, json=payload)):
                with self.assertRaises(PublishingError) as caught:
                    self.oauth.channel("secret-access-token")
                self.assertIn(message, str(caught.exception))
                self.assertNotIn("secret-access-token", str(caught.exception))
                self.assertEqual(caught.exception.kind, "needs_reauth")

    def test_failed_discovery_preserves_existing_grant(self):
        flow = Mock()
        flow.credentials.refresh_token = "new-refresh"
        flow.credentials.token = "new-access"
        self.f.store.save_state("empty-channel", {"profile_id": self.f.profile["id"], "verifier": "pkce"})
        self.f.settings.set_secret("pkce", "verifier")
        with patch.object(self.f.settings, "oauth_config", create=True, return_value={}), \
             patch("app.publishing.oauth.Flow.from_client_config", return_value=flow), \
             patch("app.publishing.oauth.httpx.get", return_value=httpx.Response(200, json={"items": []})):
            with self.assertRaises(PublishingError):
                self.oauth.finish("empty-channel", "code")
        self.assertEqual(self.f.settings.get_secret("grant:grant1"), "fake")
        self.assertIsNone(self.f.settings.get_secret("pkce"))

    def test_callback_displays_escaped_recovery_guidance(self):
        app = FastAPI()
        install_publishing(app, self.f.builder, self.f.settings)
        with TestClient(app) as client, patch.object(OAuth, "finish", side_effect=PublishingError("0 channels <test>", "needs_reauth")):
            response = client.get("/video/publishing/oauth/callback", params={"state": "fake", "code": "fake"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("0 channels &lt;test&gt;", response.text)
        self.assertIn("Do not refresh", response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_diagnostics_trace_exchange_without_exposing_secrets(self):
        flow = Mock()
        flow.credentials.token = "SECRET_ACCESS"
        flow.credentials.refresh_token = "SECRET_REFRESH"
        flow.credentials.granted_scopes = " ".join(SCOPES)
        flow.oauth2session.token = {"access_token": "SECRET_ACCESS", "refresh_token": "SECRET_REFRESH"}
        self.f.store.save_state("SECRET_STATE", {"profile_id": self.f.profile["id"], "verifier": "pkce"})
        self.f.settings.set_secret("pkce", "SECRET_PKCE")
        body = {"kind": "youtube#channelListResponse", "items": [],
                "pageInfo": {"totalResults": 0, "resultsPerPage": 5, "extra": "SECRET_BODY"},
                "unexpected": "SECRET_BODY"}
        with patch.object(self.f.settings, "oauth_config", create=True, return_value={"client_secret": "SECRET_CLIENT"}), \
             patch("app.publishing.oauth.Flow.from_client_config", return_value=flow), \
             patch("app.publishing.oauth.httpx.get", return_value=httpx.Response(200, json=body)) as get, \
             self.assertLogs("uvicorn.error.youtube_oauth", level="INFO") as logs:
            with self.assertRaises(PublishingError):
                self.oauth.finish("SECRET_STATE", "SECRET_CODE")
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer SECRET_ACCESS"})
        self.assertNotIn("SECRET_", "\n".join(logs.output))
        exchange = json.loads(logs.records[0].getMessage().split("YouTube OAuth exchange ")[1])
        discovery = json.loads(logs.records[1].getMessage().split("YouTube channels.list ")[1])
        self.assertEqual(exchange["diagnostic_id"], discovery["diagnostic_id"])
        self.assertEqual(exchange["profile_id"], self.f.profile["id"])
        self.assertTrue(exchange["token_matches_exchange"])
        self.assertTrue(all(exchange["requested_scopes_granted"].values()))
        self.assertEqual(discovery["response"]["status"], 200)
        self.assertEqual(discovery["response"]["item_count"], 0)
        self.assertEqual(discovery["response"]["pageInfo"]["totalResults"], 0)

    def test_response_diagnostics_never_dump_errors_or_non_json_bodies(self):
        for response in (
            httpx.Response(403, json={"error": {"code": 403, "message": "SECRET_MESSAGE", "errors": [{"reason": "SECRET_REASON"}]}}),
            httpx.Response(502, text="SECRET_HTML"),
            httpx.Response(200, json=["SECRET_ARRAY"]),
        ):
            result = response_diagnostic(response)
            self.assertEqual(result["status"], response.status_code)
            self.assertNotIn("SECRET_", json.dumps(result))

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
