"""Measure-first timing. Reflow automatic shots; never rewrite manual placements."""
import hashlib
import json
from mn_contracts.story import StoryProject


def scenes(project):
    return [s for a in project.arcs for c in a.chapters for s in c.scenes]


def speech_fingerprint(project, segment):
    character = next((c for c in project.characters if c.id == segment.character_id), None)
    value = {"text": segment.text, "kind": segment.kind, "character": segment.character_id,
             "voice": segment.voice or (character.voice if character else ""),
             "emotion": segment.emotion, "direction": segment.direction}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compile_timeline(project: StoryProject, chapter_id=None, scene_id=None):
    assets = {a.id: a for a in project.assets}
    selected = [s for a in project.arcs for c in a.chapters if not chapter_id or c.id == chapter_id
                for s in c.scenes if not scene_id or s.id == scene_id]
    if not selected:
        raise ValueError("No matching scenes")
    audio, visuals, layers, spans, conflicts = [], [], [], [], []
    cursor = 0.0
    for scene in selected:
        start = cursor
        local = {}
        for seg in scene.segments:
            duration = 0.0
            if seg.kind == "silence":
                duration = seg.silence_seconds
            elif not seg.audio_asset_id:
                conflicts.append(f"{seg.id}: import speech before timing/rendering")
            else:
                asset = assets[seg.audio_asset_id]
                if not asset.duration:
                    conflicts.append(f"{seg.id}: audio has no measured duration")
                else:
                    duration = asset.duration
                if asset.speech_fingerprint != speech_fingerprint(project, seg):
                    conflicts.append(f"{seg.id}: stale audio — script, voice or direction changed; import a new take")
            row = {"id": seg.id, "scene_id": scene.id, "kind": seg.kind, "start": cursor,
                   "end": cursor + duration, "duration": duration, "pause_after": seg.pause_after,
                   "asset_id": seg.audio_asset_id, "text": seg.text}
            audio.append(row)
            local[seg.id] = row
            cursor += duration + seg.pause_after
        length = cursor - start
        spans.append({"id": scene.id, "title": scene.title, "start": start, "duration": length})
        shots = []
        for i, shot in enumerate(scene.shots):
            if shot.timing == "manual":
                offset, duration = shot.start, shot.duration
            elif shot.start_segment_id:
                first, last = local[shot.start_segment_id], local[shot.end_segment_id]
                offset = first["start"] - start
                duration = last["end"] + last["pause_after"] - first["start"]
            else:
                duration = length / len(scene.shots)
                offset = duration * i
            if not shot.image_asset_id:
                conflicts.append(f"{shot.id}: attach an image")
            if duration <= 0 or offset + duration > length + .001:
                conflicts.append(f"{shot.id}: visual timing is outside the scene; manual placement was preserved")
            if shot.fade_in + shot.fade_out > duration + .001:
                conflicts.append(f"{shot.id}: fades exceed shot duration")
            row = {"id": shot.id, "scene_id": scene.id, "title": shot.title, "start": start + offset,
                   "end": start + offset + duration, "duration": duration, "asset_id": shot.image_asset_id,
                   "timing": shot.timing, "fit": shot.fit, "motion": shot.motion,
                   "fade_in": shot.fade_in, "fade_out": shot.fade_out}
            shots.append(row)
        edge = start
        for shot in sorted(shots, key=lambda x: x["start"]):
            if abs(shot["start"] - edge) > .001:
                conflicts.append(f"{shot['id']}: visual gap/overlap; adjust placement explicitly")
            edge = shot["end"]
        if abs(edge - cursor) > .001 or not shots:
            conflicts.append(f"{scene.id}: images must cover the complete scene")
        visuals.extend(shots)
        for layer in scene.audio_layers:
            asset = assets[layer.audio_asset_id]
            if not asset.duration or (not layer.loop and layer.duration > asset.duration + .001):
                conflicts.append(f"{layer.id}: layer needs a long enough audio file or loop enabled")
            if layer.start + layer.duration > length + .001 or layer.fade_in + layer.fade_out > layer.duration:
                conflicts.append(f"{layer.id}: layer/fades exceed scene duration")
            layers.append({**layer.model_dump(), "start": start + layer.start, "scene_id": scene.id})
    return {"project_id": project.id, "revision": project.revision, "duration": cursor,
            "scenes": spans, "audio": audio, "visuals": visuals, "layers": layers,
            "conflicts": conflicts, "ready": not conflicts and cursor > 0,
            "timing_basis": "measured_audio_plus_explicit_silence"}
