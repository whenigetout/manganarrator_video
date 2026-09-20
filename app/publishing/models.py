"""Publishing contracts deliberately separate from legacy render job contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.domain import AudioVideoRequest


class PublishingError(Exception):
    def __init__(self, message, kind="failed", delay=0):
        super().__init__(message)
        self.kind, self.delay = kind, delay


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Provider(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(default="https://api.deepseek.com", max_length=500)
    model: str = Field(min_length=1, max_length=200)
    json_mode: Literal["json_object", "text"] = "json_object"
    timeout: int = Field(default=90, ge=5, le=180)

    @model_validator(mode="after")
    def secure_url(self):
        from urllib.parse import urlsplit
        url = urlsplit(self.base_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Provider URL must be HTTPS without credentials, query or fragment")
        return self


class Profile(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    preset: dict = Field(default_factory=dict)
    provider_id: str = Field(default="", max_length=100)
    prompt: str = Field(default="Write clear, accurate metadata for my recording. Do not invent credits, lyrics or claims.", max_length=12000)
    category: str = Field(default="10", pattern=r"^\d{1,3}$")
    tags: list[str] = Field(default_factory=list, max_length=100)
    privacy: Literal["private", "unlisted"] = "private"
    language: str = Field(default="en", max_length=20)
    made_for_kids: bool = False
    contains_synthetic_media: bool = False

    @model_validator(mode="after")
    def valid_preset(self):
        preset = dict(self.preset)
        for key in ("audio_ref", "source_name", "run_id", "preview_seconds"):
            preset.pop(key, None)
        request = AudioVideoRequest.model_validate({**preset, "audio_ref": {"namespace": "outputs", "path": "pending.wav"}})
        self.preset = request.model_dump(mode="json", exclude={"audio_ref", "source_name", "run_id", "preview_seconds"})
        validate_tags(self.tags)
        return self


def validate_tags(tags):
    if any(not tag.strip() or "<" in tag or ">" in tag for tag in tags):
        raise ValueError("Tags must be nonempty and cannot contain angle brackets")
    # YouTube counts separators and quotes around tags containing spaces.
    cost = sum(len(tag) + (2 if " " in tag else 0) for tag in tags) + max(0, len(tags) - 1)
    if cost > 500:
        raise ValueError("Tags exceed YouTube's 500-character combined limit")


class Metadata(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def youtube_limits(self):
        if len(self.description.encode("utf-8")) > 5000:
            raise ValueError("Description exceeds 5000 UTF-8 bytes")
        if any(c in self.title + self.description for c in "<>"):
            raise ValueError("Title and description cannot contain angle brackets")
        self.tags = list(dict.fromkeys(tag.strip() for tag in self.tags))
        validate_tags(self.tags)
        return self


class RunInput(StrictModel):
    profile_id: str
    audio_ref: dict
    source_name: str = Field(min_length=1, max_length=255)
    context: str = Field(default="", max_length=20000)
    transcript: str = Field(default="", max_length=100000)
    config: dict | None = None


class Review(StrictModel):
    revision: int = Field(ge=1)
    metadata: Metadata
    privacy: Literal["private", "unlisted", "public"] = "private"
    category: str = Field(default="10", pattern=r"^\d{1,3}$")
    made_for_kids: bool
    contains_synthetic_media: bool
    confirm_public: bool = False

    @model_validator(mode="after")
    def explicit_public(self):
        if self.privacy == "public" and not self.confirm_public:
            raise ValueError("Public visibility requires explicit confirmation")
        return self
