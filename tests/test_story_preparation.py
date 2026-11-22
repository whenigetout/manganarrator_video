import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.story.preparation import create_app


DEMO = Path(__file__).parents[1] / "fixtures" / "story-demo.md"


class PreparationTests(unittest.TestCase):
    def test_requires_explicit_absolute_storage(self):
        for settings in ({}, {"STORY_STUDIO_ROOT": "relative"}):
            with patch.dict(os.environ, settings, clear=True), self.assertRaises(RuntimeError):
                create_app()

    def test_authenticated_preparation_can_add_a_scene(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, STORY_STUDIO_ROOT=root, STORY_SHARED_TOKEN="test-only"
        ), TestClient(create_app()) as client:
            self.assertEqual(client.get("/video/story/projects").status_code, 401)
            client.headers["Authorization"] = "Bearer test-only"
            response = client.post("/video/story/import", json={
                "format": "markdown", "content": DEMO.read_text(encoding="utf-8"),
            })
            self.assertEqual(response.status_code, 200, response.text)
            draft = response.json()
            chapter = draft["arcs"][0]["chapters"][0]
            chapter["scenes"].append({
                "id": "new-scene", "title": "New scene",
                "segments": [{"id": "new-line", "kind": "narration", "text": "A new draft."}],
            })
            response = client.put(f"/video/story/projects/{draft['id']}", json=draft)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_shared_edits_revision_conflict_and_restart(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, STORY_STUDIO_ROOT=root):
            app = create_app()
            with TestClient(app) as tablet, TestClient(app) as desktop:
                response = tablet.post("/video/story/import", json={
                    "format": "markdown", "content": DEMO.read_text(encoding="utf-8"),
                })
                self.assertEqual(response.status_code, 200, response.text)
                original = response.json()
                url = f"/video/story/projects/{original['id']}"
                tablet_draft = tablet.get(url).json()
                desktop_draft = desktop.get(url).json()
                tablet_draft["arcs"][0]["chapters"][0]["title"] = "Tablet chapter"
                self.assertEqual(tablet.put(url, json=tablet_draft).status_code, 200)

                desktop_draft["title"] = "Stale edit"
                self.assertEqual(desktop.put(url, json=desktop_draft).status_code, 409)
                desktop_draft = desktop.get(url).json()
                self.assertEqual(desktop_draft["arcs"][0]["chapters"][0]["title"], "Tablet chapter")

                desktop_draft["arcs"][0]["chapters"][0]["title"] = "Desktop chapter"
                response = desktop.put(url, json=desktop_draft)
                self.assertEqual(response.status_code, 200, response.text)
                saved = response.json()
                self.assertEqual(tablet.get(url).json(), saved)

                image = io.BytesIO()
                Image.new("RGB", (8, 8), "navy").save(image, format="PNG")
                response = tablet.post(f"{url}/assets", data={"kind": "image", "revision": saved["revision"]},
                                       files={"file": ("scene.png", image.getvalue(), "image/png")})
                self.assertEqual(response.status_code, 200, response.text)
                saved = response.json()["project"]
                asset_url = f"{url}/assets/{response.json()['asset']['id']}"
                asset = desktop.get(asset_url)
                self.assertEqual(asset.status_code, 200)
                self.assertEqual(asset.headers["content-type"], "image/png")
                self.assertEqual(tablet.get(f"{url}/renders").status_code, 404)
                self.assertEqual(tablet.get("/video/status/example").status_code, 404)

            with TestClient(create_app()) as restarted:
                self.assertEqual(restarted.get(url).json(), saved)
                self.assertEqual(restarted.get(f"{url}/history").json(), [0, 1, 2, 3])
                self.assertEqual(restarted.get(asset_url).content, asset.content)
