"""Explicit Markdown grammar; raw chat exports require editorial normalization."""
import json
import re
from mn_contracts.story import StoryProject

HEADER = re.compile(r"^(#{1,4}) (.+?) \{#([A-Za-z0-9][A-Za-z0-9_-]{0,95})\}$")
LINE = re.compile(r"^\[([A-Za-z0-9][A-Za-z0-9_-]{0,95})\]\s+(NARRATOR|[A-Za-z0-9_-]+|PAUSE):\s*(.+)$")


def import_story(content: str, kind: str) -> StoryProject:
    if kind == "json":
        return StoryProject.model_validate(json.loads(content))
    if kind != "markdown":
        raise ValueError("Use json or markdown")
    data = {"id": "import", "title": "", "arcs": [], "characters": []}
    arc = chapter = scene = None
    char_ids = set()
    for number, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        h = HEADER.match(line)
        if h:
            level, title, identifier = len(h[1]), h[2], h[3]
            if level == 1:
                if data["title"]:
                    raise ValueError(f"Line {number}: only one series title is allowed")
                data.update(id=identifier, title=title, series_title=title)
            elif level == 2 and data["title"]:
                arc = {"id": identifier, "title": title, "chapters": []}
                data["arcs"].append(arc)
                chapter = scene = None
            elif level == 3 and arc:
                chapter = {"id": identifier, "title": title, "scenes": []}
                arc["chapters"].append(chapter)
                scene = None
            elif level == 4 and chapter:
                scene = {"id": identifier, "title": title, "canonical_text": "", "segments": [], "shots": []}
                chapter["scenes"].append(scene)
            else:
                raise ValueError(f"Line {number}: headings must nest series → arc → chapter → scene")
            continue
        m = LINE.match(line)
        if not m or scene is None:
            raise ValueError(f"Line {number}: expected a structured heading or [stable-id] SPEAKER: text; normalize chat/OOC first")
        identifier, speaker, text = m.groups()
        segment = {"id": identifier, "kind": "narration", "text": text}
        if speaker == "PAUSE":
            segment.update(kind="silence", text="", silence_seconds=float(text))
        elif speaker != "NARRATOR":
            segment.update(kind="dialogue", character_id=speaker)
            if speaker not in char_ids:
                data["characters"].append({"id": speaker, "name": speaker.replace("_", " ")})
                char_ids.add(speaker)
        scene["segments"].append(segment)
        scene["canonical_text"] += ("\n" if scene["canonical_text"] else "") + line
    return StoryProject.model_validate(data)
