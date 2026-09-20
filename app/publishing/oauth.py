"""Google grants bound to verified channel identities, not account display names."""
import json
import secrets
import threading
import uuid
import httpx
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError, TransportError
from .models import PublishingError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


class OAuth:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.lock = threading.RLock()

    def import_client(self, config):
        web = config.get("web", {})
        if not isinstance(web, dict) or not web.get("client_id") or not web.get("client_secret"):
            raise ValueError("Choose the JSON for a Google OAuth Web application client")
        if web.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth" or web.get("token_uri") != "https://oauth2.googleapis.com/token":
            raise ValueError("The JSON must use Google's official OAuth endpoints")
        self.settings.set_secret("google_client", json.dumps({"web": web}))

    def begin(self, profile_id):
        profile = self.store.get("profiles", profile_id)
        flow = Flow.from_client_config(self.settings.oauth_config(), scopes=SCOPES,
                                      redirect_uri=self.settings.redirect_uri, autogenerate_code_verifier=True)
        url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
        verifier_key = "pkce:" + secrets.token_hex(16)
        self.settings.set_secret(verifier_key, flow.code_verifier)
        expired = self.store.save_state(state, {"profile_id": profile_id, "channel_id": profile.get("channel_id"), "verifier": verifier_key})
        for old in expired:
            self.settings.delete_secret(old["verifier"])
        return url

    def finish(self, state, code):
        data = self.store.consume_state(state)
        verifier = self.settings.get_secret(data["verifier"])
        self.settings.delete_secret(data["verifier"])
        flow = Flow.from_client_config(self.settings.oauth_config(), scopes=SCOPES, state=state,
                                      redirect_uri=self.settings.redirect_uri, code_verifier=verifier)
        try:
            flow.fetch_token(code=code, timeout=30)
        except Exception as exc:
            raise ValueError("Google authorization failed. Connect again and grant both requested permissions.") from exc
        if not flow.credentials.refresh_token:
            raise ValueError("Google did not issue offline access. Reconnect and grant access.")
        channel = self.channel(flow.credentials.token)
        with self.lock:
            profile = self.store.get("profiles", data["profile_id"])
            expected = profile.get("channel_id") or data.get("channel_id")
            if expected and expected != channel["id"]:
                raise ValueError("Wrong YouTube channel. This profile is already bound to a different channel.")
            credential_id = profile.get("credential_id") or uuid.uuid4().hex
            self.settings.set_secret("grant:" + credential_id, flow.credentials.to_json())
            profile.update(channel_id=channel["id"], channel_name=channel["snippet"]["title"], credential_id=credential_id)
            self.store.put("profiles", profile, profile["id"])
        return profile

    def credentials(self, profile, force=False):
        with self.lock:
            raw = self.settings.get_secret("grant:" + profile.get("credential_id", ""))
            if not raw:
                raise PublishingError("Channel disconnected. Connect this profile in Channel profiles, then retry.", "needs_reauth")
            credentials = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
            if force or not credentials.valid:
                try:
                    credentials.refresh(Request())
                except RefreshError as exc:
                    raise PublishingError("Google access expired or was revoked. Reconnect this channel, then retry.", "needs_reauth") from exc
                except TransportError as exc:
                    raise PublishingError("Google token service unavailable. Retrying.", "retry_wait") from exc
                self.settings.set_secret("grant:" + profile["credential_id"], credentials.to_json())
            return credentials

    @staticmethod
    def channel(token):
        try:
            response = httpx.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "id,snippet", "mine": "true"},
                                 headers={"Authorization": "Bearer " + token}, timeout=30)
        except httpx.TransportError as exc:
            raise PublishingError("Cannot verify the channel. Retrying.", "retry_wait") from exc
        if response.status_code != 200:
            raise PublishingError("Cannot verify channel ownership. Reconnect with YouTube read and upload access.", "needs_reauth")
        items = response.json().get("items", [])
        if len(items) != 1:
            raise PublishingError("Google must authorize exactly one YouTube channel. Reconnect and choose that channel.", "needs_reauth")
        return items[0]

    def verify(self, profile):
        credentials = self.credentials(profile)
        channel = self.channel(credentials.token)
        if channel["id"] != profile.get("channel_id"):
            raise PublishingError("Channel identity mismatch. Upload blocked; reconnect the correct channel.", "needs_reauth")
        return credentials

    def disconnect(self, profile):
        # Delete this independent local grant. Google account-wide revocation can
        # revoke other profiles sharing the same OAuth client, so it is not automatic.
        with self.lock:
            self.settings.delete_secret("grant:" + profile.get("credential_id", ""))
