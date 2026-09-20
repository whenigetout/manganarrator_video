import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
from google.auth.exceptions import RefreshError
from app.publishing.oauth import OAuth
from app.publishing.models import PublishingError
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
