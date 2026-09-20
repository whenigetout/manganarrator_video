import tempfile
from pathlib import Path
from types import SimpleNamespace
from app.publishing.models import Profile, RunInput
from app.publishing.store import Store
from app.publishing.workflow import Workflow


class MemorySettings:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.secrets = {}
        self.origins = {"http://testserver"}
        self.redirect_uri = "http://testserver/video/publishing/oauth/callback"
    def get_secret(self, key): return self.secrets.get(key)
    def set_secret(self, key, value): self.secrets[key] = value
    def delete_secret(self, key): self.secrets.pop(key, None)
    def owner_key(self): return "test-owner-key-not-a-real-secret"


class Fixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = MemorySettings(self.root)
        self.store = Store(self.root / "publishing.db")
        self.builder = SimpleNamespace(config=SimpleNamespace(media_root=self.root / "media"))
        self.workflow = Workflow(self.builder, self.settings, self.store, None)
        self.profile = self.store.put("profiles", {**Profile(name="Singing").model_dump(), "channel_id": "UC_test", "channel_name": "Singing channel", "credential_id": "grant1"})
        self.settings.set_secret("grant:grant1", "fake")
        self.source = self.root / "media/outputs/audio_video_uploads/test.wav"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"fixture-audio")
        self.request = RunInput(profile_id=self.profile["id"], audio_ref={"namespace":"outputs","path":"audio_video_uploads/test.wav"}, source_name="My recording.wav")
    def run(self): return self.workflow.create(self.request, "test-key-123")
    def rendered(self, run):
        from mn_contracts.ocr import MediaRef
        from app.publishing.workflow import file_identity
        path = self.root / "media/outputs/audio_video/result.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-video")
        ref = MediaRef(namespace="outputs", path="audio_video/result.mp4").model_dump(mode="json")
        return self.store.change(run["id"], {"artifact":{"ref":ref,"identity":file_identity(path)},"state":"generating_metadata"})
    def close(self): self.temp.cleanup()
