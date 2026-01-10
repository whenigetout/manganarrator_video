
from pathlib import Path
from app.backends.ffmpeg_backend import FClip

img = "input/images/a_returners_magic_should_be_special_6_1.jpg"
out = "output/test"

clip = (
    FClip.image(img)
    .crop(720, 1920, 0, 0)
    .pad(w=800, h=2000, x=40, y=40, color="pink")
    .trim(end=6)
    .fade_in(duration=1)
    .fade_out(start=4, duration=2)
    .output(f"{out}/still.mp4")
)
