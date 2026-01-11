from pathlib import Path
import ffmpeg

IMG = "input/images/a_returners_magic_should_be_special_6_1.jpg"
AUDIO = "input/audio/voice1.wav"

OUT = Path("output/tests")
OUT.mkdir(parents=True, exist_ok=True)

out_path = OUT / "clip2_raw_ffmpeg.mp4"

# ----------------------------
# Video: still image → crop → pad → fade → duration
# ----------------------------

video = (
    ffmpeg
    .input(
        IMG,
        loop=1,
        framerate=24,
        t=3.0,              # explicit duration
    )
    .filter("crop", 720, 1920, 0, 1000)
    .filter("pad", 800, 2000, 40, 40, color="green")
    .filter("fade", t="in", st=0, d=0.5)
    .filter("setpts", "PTS-STARTPTS")
)

# ----------------------------
# Audio: file → resample → trim → reset timestamps
# ----------------------------

audio = (
    ffmpeg
    .input(AUDIO)
    .filter("atrim", start=0, end=3.0)
    .filter("asetpts", "PTS-STARTPTS")
    .filter("aresample", 44100)
)

# ----------------------------
# Output (matches your FClip defaults)
# ----------------------------

(
    ffmpeg
    .output(
        video,
        audio,
        str(out_path),
        vcodec="h264_nvenc",
        pix_fmt="yuv420p",
        r=24,
        acodec="aac",
        audio_bitrate="192k",
    )
    .overwrite_output()
    .run()
)

print("OK: clip2_raw_ffmpeg.mp4 rendered")
