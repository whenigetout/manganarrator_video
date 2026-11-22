"""Local project/revision store. One server worker; optimistic revisions prevent lost edits."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import uuid

from mn_contracts.story import StoryProject, StoryAsset
from .timeline import scenes, speech_fingerprint


class Conflict(ValueError):
    pass


def safe_id(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise ValueError("Invalid identifier")
    return value


def probe_duration(path):
    data = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=duration:format=duration", "-of", "json", str(path)], timeout=30))
    if not data.get("streams"):
        raise ValueError("No readable audio stream")
    value = float(data["streams"][0].get("duration") or data["format"]["duration"])
    if not 0 < value <= 86400:
        raise ValueError("Invalid audio duration")
    return value


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class StoryStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def folder(self, identifier):
        path = (self.root / safe_id(identifier)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Project path escapes storage")
        return path

    def read(self, identifier):
        with self.lock:
            folder = self.folder(identifier)
            if (folder / ".deleted").exists():
                raise FileNotFoundError(identifier)
            return StoryProject.model_validate_json((folder / "project.json").read_text(encoding="utf-8"))

    def delete(self, identifier, expected_revision):
        with self.lock:
            if self.read(identifier).revision != expected_revision:
                raise Conflict("The project changed. Reopen it before deleting.")
            (self.folder(identifier) / ".deleted").touch(exist_ok=False)

    def list(self):
        result = []
        for file in sorted(self.root.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                project = self.read(file.parent.name)
            except FileNotFoundError:
                continue
            result.append({"id": project.id, "title": project.title, "series_title": project.series_title,
                           "revision": project.revision})
        return result

    def _write(self, project):
        folder = self.folder(project.id)
        (folder / "history").mkdir(parents=True, exist_ok=True)
        text = project.model_dump_json(indent=2)
        # Revisions are immutable; current project is replaced atomically.
        (folder / "history" / f"{project.revision}.json").write_text(text, encoding="utf-8")
        temp = folder / "project.tmp"
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, folder / "project.json")
        return project

    def create(self, project):
        with self.lock:
            if project.assets:
                raise ValueError("Import manuscript JSON without local assets; use Duplicate draft to retain uploaded media")
            project = project.model_copy(deep=True)
            project.id = "story_" + uuid.uuid4().hex
            project.revision = 0
            return self._write(project)

    def save(self, identifier, proposed, expected_revision, *, allow_new_scenes=False):
        with self.lock:
            current = self.read(identifier)
            if current.revision != expected_revision:
                raise Conflict("Project changed elsewhere. Reload before saving; your edit was not applied.")
            if proposed.id != identifier or proposed.assets != current.assets:
                raise ValueError("Project identity and asset metadata are managed by the server")
            old = {s.id: s for s in scenes(current)}
            new = {s.id: s for s in scenes(proposed)}
            if not old.keys() <= new.keys() or (not allow_new_scenes and old.keys() != new.keys()):
                raise ValueError("This slice preserves imported scenes; import a new manuscript to change scene structure")
            for key, previous in old.items():
                candidate = new[key]
                if (previous.canonical_text, previous.source_refs) != (candidate.canonical_text, candidate.source_refs):
                    raise ValueError("Canonical source is immutable; edit draft segments instead")
                if previous.locked and previous.model_dump(exclude={"locked"}) != candidate.model_dump(exclude={"locked"}):
                    raise Conflict(f"Scene {key} is locked; unlock and save before changing it")
            # A character voice change also affects locked dialogue scenes.
            for scene in old.values():
                if scene.locked:
                    for seg in scene.segments:
                        if speech_fingerprint(current, seg) != speech_fingerprint(proposed, seg):
                            raise Conflict(f"Scene {scene.id} is locked; its character voice cannot change")
            proposed.revision = current.revision + 1
            return self._write(proposed)

    def history(self, identifier):
        self.read(identifier)
        return sorted(int(p.stem) for p in (self.folder(identifier) / "history").glob("*.json"))

    def restore(self, identifier, revision, expected):
        with self.lock:
            if revision < 0:
                raise ValueError("Invalid revision")
            current = self.read(identifier)
            old = StoryProject.model_validate_json((self.folder(identifier) / "history" / f"{revision}.json").read_text(encoding="utf-8"))
            old.assets = current.assets  # retain all takes, including later imports
            return self.save(identifier, old, expected)

    def duplicate(self, identifier, expected):
        with self.lock:
            old = self.read(identifier)
            if old.revision != expected:
                raise Conflict("Reload before duplicating")
            new = old.model_copy(deep=True)
            new.id = "story_" + uuid.uuid4().hex
            new.title += " — draft"
            new.revision = 0
            source = self.folder(identifier) / "assets"
            if source.exists():
                shutil.copytree(source, self.folder(new.id) / "assets")
            return self._write(new)

    def asset_path(self, project, asset):
        folder = (self.folder(project.id) / "assets").resolve()
        path = (folder / asset.filename).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise FileNotFoundError("Asset not found in this project")
        return path

    def upload(self, identifier, upload, kind, expected, segment_id=None):
        with self.lock:
            project = self.read(identifier)
            if project.revision != expected:
                raise Conflict("Reload before importing media")
            segment = None
            if segment_id:
                for scene in scenes(project):
                    for s in scene.segments:
                        if s.id == segment_id:
                            if scene.locked:
                                raise Conflict("Unlock the scene before importing a take")
                            if s.kind == "silence":
                                raise ValueError("Silence segments do not accept audio")
                            segment = s
                if segment is None or kind != "audio":
                    raise ValueError("Unknown spoken segment")
            folder = self.folder(identifier) / "assets"
            folder.mkdir(exist_ok=True)
            identifier_asset = "asset_" + uuid.uuid4().hex
            suffix = Path(upload.filename or "").suffix.lower()
            allowed = {"audio": {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"},
                       "image": {".png", ".jpg", ".jpeg", ".webp"}}
            if kind not in allowed or suffix not in allowed[kind]:
                raise ValueError("Unsupported media extension")
            target = folder / (identifier_asset + (".wav" if kind == "audio" else ".png"))
            try:
                with tempfile.TemporaryDirectory(dir=folder) as tmp:
                    source = Path(tmp) / ("upload" + suffix)
                    total = 0
                    with source.open("wb") as handle:
                        while chunk := upload.file.read(1024 * 1024):
                            total += len(chunk)
                            if total > 100 * 1024 * 1024:
                                raise ValueError("Each story asset must be under 100 MB")
                            handle.write(chunk)
                    if kind == "audio":
                        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-map", "0:a:0",
                            "-vn", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(target)],
                            check=True, capture_output=True, timeout=180)
                        duration = probe_duration(target)
                    else:
                        from PIL import Image, ImageOps
                        with Image.open(source) as img:
                            if img.width * img.height > 32_000_000:
                                raise ValueError("Image exceeds 32 megapixels")
                            ImageOps.exif_transpose(img).convert("RGB").save(target)
                        duration = None
                asset = StoryAsset(id=identifier_asset, kind=kind, filename=target.name,
                    original_name=Path(upload.filename or "upload").name, duration=duration, sha256=digest(target),
                    speech_fingerprint=speech_fingerprint(project, segment) if segment else None)
                project.assets.append(asset)
                if segment:
                    segment.audio_asset_id = asset.id
                project.revision += 1
                self._write(project)
                return project, asset
            except Exception:
                target.unlink(missing_ok=True)
                raise
            finally:
                upload.file.close()
