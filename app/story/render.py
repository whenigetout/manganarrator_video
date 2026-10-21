"""Measured story timeline → FFmpeg, reusing the existing clip/concat backend."""
from pathlib import Path
import json
import math
import shutil
import wave
import ffmpeg

from app.backends.ffmpeg_backend.clip import FClip
from app.backends.ffmpeg_backend.concat import concat_files
from .store import digest, probe_duration
from .timeline import compile_timeline


def _silence(output, seconds):
    samples = round(seconds * 48000)
    while samples:
        n = min(samples, 48000)
        output.writeframesraw(b"\0" * n * 4)
        samples -= n


def render_story(store, project, output_dir, chapter_id=None, scene_id=None,
                 width=1280, height=720, fps=24, progress=lambda *_: None):
    timeline = compile_timeline(project, chapter_id, scene_id)
    if not timeline["ready"]:
        raise ValueError("Resolve timeline conflicts before rendering: " + "; ".join(timeline["conflicts"]))
    if timeline["duration"] > 7200:
        raise ValueError("Render one chapter at a time (maximum two hours)")
    assets = {a.id: a for a in project.assets}
    used = {r["asset_id"] for r in timeline["audio"] + timeline["visuals"] if r["asset_id"]}
    used.update(r["audio_asset_id"] for r in timeline["layers"])
    paths = {}
    for identifier in used:
        asset = assets[identifier]
        path = store.asset_path(project, asset)
        if digest(path) != asset.sha256:
            raise ValueError(f"Asset {identifier} changed outside the project; import it again")
        if asset.kind == "audio" and abs(probe_duration(path) - asset.duration) > .001:
            raise ValueError(f"Asset {identifier} duration changed; import it again")
        paths[identifier] = path
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    temp = output_dir / "tmp"
    temp.mkdir()
    try:
        progress(5, "Assembling measured dialogue")
        speech = temp / "speech.wav"
        with wave.open(str(speech), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(48000)
            for row in timeline["audio"]:
                if row["kind"] == "silence":
                    _silence(out, row["duration"])
                else:
                    with wave.open(str(paths[row["asset_id"]]), "rb") as take:
                        if (take.getnchannels(), take.getsampwidth(), take.getframerate()) != (2, 2, 48000):
                            raise ValueError("Speech must be imported through the asset endpoint")
                        while chunk := take.readframes(48000):
                            out.writeframesraw(chunk)
                _silence(out, row["pause_after"])
        clips = []
        commands = []
        ordered = sorted(timeline["visuals"], key=lambda row: row["start"])
        for i, shot in enumerate(ordered):
            progress(10 + 65 * i / len(ordered), f"Rendering shot {i + 1}/{len(ordered)}")
            start_frame = round(shot["start"] * fps)
            end_frame = round(shot["end"] * fps)
            if i == len(ordered) - 1:
                end_frame = math.ceil(timeline["duration"] * fps)
            frames = end_frame - start_frame
            if frames < 1:
                raise ValueError(f"{shot['id']}: shot is shorter than one output frame")
            duration = frames / fps
            clip = FClip.still(paths[shot["asset_id"]], duration=duration, fps=fps)
            mode = "increase" if shot["fit"] == "cover" else "decrease"
            clip.v = clip.v.filter("scale", width, height, force_original_aspect_ratio=mode)
            if mode == "increase":
                clip.v = clip.v.filter("crop", width, height)
            else:
                clip.v = clip.v.filter("pad", width, height, "(ow-iw)/2", "(oh-ih)/2")
            clip.v = clip.v.filter("setsar", 1)
            if shot["motion"] == "slow_zoom":
                clip.v = clip.v.filter("zoompan", z=f"min(1+on*0.04/{frames},1.04)",
                    x="iw/2-iw/zoom/2", y="ih/2-ih/zoom/2", d=1, s=f"{width}x{height}", fps=fps)
            if shot["fade_in"]:
                clip.fade_in(min(shot["fade_in"], duration))
            if shot["fade_out"]:
                clip.fade_out(min(shot["fade_out"], duration), max(0, duration - shot["fade_out"]))
            dest = temp / f"shot_{i:04d}.mp4"
            stream = ffmpeg.output(clip.v, str(dest), vcodec="libx264", preset="veryfast", crf=20,
                pix_fmt="yuv420p", r=fps, vframes=frames, threads=2).global_args("-filter_threads", "1", "-filter_complex_threads", "1")
            commands.append(ffmpeg.compile(stream))
            stream.run(quiet=True, overwrite_output=True)
            clips.append(dest)
        progress(80, "Joining visuals and mixing sound")
        visual = temp / "visual.mp4"
        concat_files(clips, visual)
        tracks = [ffmpeg.input(str(speech)).audio]
        for layer in timeline["layers"]:
            opts = {"stream_loop": -1} if layer["loop"] else {}
            track = ffmpeg.input(str(paths[layer["audio_asset_id"]]), **opts).audio
            track = track.filter("atrim", duration=layer["duration"]).filter("asetpts", "PTS-STARTPTS")
            track = track.filter("aresample", 48000).filter("volume", layer["gain"])
            if layer["fade_in"]:
                track = track.filter("afade", t="in", st=0, d=layer["fade_in"])
            if layer["fade_out"]:
                track = track.filter("afade", t="out", st=layer["duration"] - layer["fade_out"], d=layer["fade_out"])
            track = track.filter("adelay", round(layer["start"] * 1000), all=1)
            tracks.append(track)
        audio = tracks[0] if len(tracks) == 1 else ffmpeg.filter(tracks, "amix", inputs=len(tracks), duration="first", normalize=0)
        audio = audio.filter("alimiter", limit=.95, level=False, latency=True)
        stream = ffmpeg.output(ffmpeg.input(str(visual)).video, audio, str(output_dir / "episode.mp4"),
            vcodec="copy", acodec="aac", audio_bitrate="192k", t=timeline["duration"], movflags="+faststart")
        commands.append(ffmpeg.compile(stream))
        stream.run(quiet=True, overwrite_output=True)
        # Manifest is local/private, contains the exact script revision and measured timeline.
        manifest = {"schema_version": "1.0", "project": project.model_dump(), "timeline": timeline,
                    "render": {"width": width, "height": height, "fps": fps, "encoder": "libx264",
                               "chapter_id": chapter_id, "scene_id": scene_id,
                               "visual_transition": "cut_or_fade_through_black"},
                    "commands": commands, "output_sha256": digest(output_dir / "episode.mp4")}
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        progress(100, "Complete")
        return manifest
    except ffmpeg.Error as exc:
        raise ValueError("FFmpeg failed: " + (exc.stderr or b"").decode(errors="replace")[-3000:]) from exc
    finally:
        shutil.rmtree(temp, ignore_errors=True)
