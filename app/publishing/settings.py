"""User-local state and OS-backed secrets; never fall back to plaintext tokens."""
import hashlib
import json
import os
import secrets
from pathlib import Path


class Settings:
    def __init__(self, directory=None):
        default = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "MangaNarrator/publishing"
        self.directory = Path(directory or os.environ.get("PUBLISHING_STATE_DIR", default)).resolve()
        repo = Path(__file__).resolve().parents[2]
        if self.directory.is_relative_to(repo):
            raise ValueError("Publishing state must be outside the repository")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.origins = set(os.environ.get("PUBLISHING_ORIGINS", "http://127.0.0.1:8084,http://localhost:8084,http://127.0.0.1:5173,http://localhost:5173").split(","))
        self.redirect_uri = os.environ.get("PUBLISHING_REDIRECT_URI", "http://127.0.0.1:8084/video/publishing/oauth/callback")
        self.service = "MangaNarratorPublishing-" + hashlib.sha256(str(self.directory).encode()).hexdigest()[:16]

    def get_secret(self, name):
        import keyring
        return keyring.get_password(self.service, name)

    def set_secret(self, name, value):
        import keyring
        keyring.set_password(self.service, name, value)

    def delete_secret(self, name):
        import keyring
        if self.get_secret(name) is not None:
            keyring.delete_password(self.service, name)

    def owner_key(self):
        key = self.get_secret("owner")
        if not key:
            key = secrets.token_urlsafe(48)
            self.set_secret("owner", key)
        return key

    def oauth_config(self):
        raw = self.get_secret("google_client")
        if not raw:
            raise ValueError("Import your Google OAuth web client JSON in Publishing setup")
        return json.loads(raw)
