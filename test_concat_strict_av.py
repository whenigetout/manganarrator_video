from pathlib import Path
from app.backends.ffmpeg_backend.clip import FClip
from app.backends.ffmpeg_backend.concat import concat_clips

OUT = Path("output/tests")
OUT.mkdir(parents=True, exist_ok=True)

IMG = "input/images/a_returners_magic_should_be_special_6_1.jpg"
AUDIO1 = "input/audio/voice1.wav"
AUDIO2 = "input/audio/voice2.wav"

# -------------------------------------------------
# Clip 1: Image + silence (2s)
# -------------------------------------------------

clip1 = (
    FClip.still(IMG, duration=2.0)
    .crop(720, 1920, 0, 0)
    .pad(800, 2000, 40, 40, color="pink")
    .fade_in(0.5)
    .ensure_audio_track(duration=2.0)
)

# -------------------------------------------------
# Clip 2: Image + voice (3s)
# -------------------------------------------------

clip2 = (
    FClip.still(IMG, duration=3.0)
    .crop(720, 1920, 0, 1000)
    .pad(800, 2000, 40, 40, color="green")
    .with_audio(AUDIO1)
    .fade_in(0.5)
)

# -------------------------------------------------
# Clip 3: Black screen + voice (1.5s)
# -------------------------------------------------

clip3 = (
    FClip.color(
        "black",
        width=800,
        height=2000,
        duration=1.5,
    )
    .with_audio(AUDIO2)
)

# -------------------------------------------------
# Concat (STRICT: AV only)
# -------------------------------------------------

final = concat_clips([
    clip1,
    clip2,
    clip3,
])

# -------------------------------------------------
# Output
# -------------------------------------------------

out_path = OUT / "concat_strict_av.mp4"
final.output(out_path)

print(f"OK: rendered {out_path}")
print("⚠️  DO NOT play inside VS Code. Use VLC or ffplay.")
