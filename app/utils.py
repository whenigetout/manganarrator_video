from pathlib import Path
import time
from rich.console import Console
import sys
import threading
import soundfile as sf
import traceback
import mn_contracts.ocr as o
import app.models.domain as d
import mn_contracts.pcc_backend as p

def log_exception(context: str = "Unhandled exception", label: str = "💀"):
    print(f"\n{label} {context}:")
    traceback.print_exc()

# --- Console Color Helpers ---
class LogColor:
    RESET = "\033[0m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"

def log(msg: str, color=LogColor.CYAN, indent: int = 0):
    prefix = "    " * indent
    print(f"{color}{prefix}{msg}{LogColor.RESET}")


def ensure_folder(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def get_audio_duration(path: Path) -> float:
    with sf.SoundFile(path) as f:
        return len(f) / f.samplerate

def build_video_dialogues_for_image(
    run_id: str,
    img: o.OCRImage,
    media_root: str
) -> dict[int, d.VideoDialogueLine]:
    video_dialogues = {}

    img_ref = img.image_info.image_ref

    for dlg in img.dialogue_lines:
        if dlg.original_bbox is None:
            print(f"[video] Warning: dialogue line id={dlg.id} on image {img.image_info.image_ref.path} has no bbox — skipping from video")
            continue

        audio_ref = p.latest_tts_audio_ref(
            run_id=run_id,
            dlg_id=dlg.id,
            img_ref=img_ref,
            media_root=media_root
        )

        video_dialogues[dlg.id] = d.VideoDialogueLine(
            id=dlg.id,
            image_id=dlg.image_id,
            text=dlg.text,
            speaker=dlg.speaker,
            emotion=dlg.emotion,
            original_bbox=dlg.original_bbox,
            audio_ref=audio_ref
        )

    return video_dialogues

class Timer:
    last_duration = 0.0

    def __init__(self, label: str = "", use_spinner: bool = True, show_elapsed: bool = False):
        self.label = label
        self.start_time = None
        self.use_spinner = use_spinner
        self.show_elapsed = show_elapsed
        self.console = Console()
        self.status = None
        self._ticker = None

    def __enter__(self):
        if self.use_spinner:
            self.status = self.console.status(
                f"[bold cyan]{self.label}...[/]",
                spinner="bouncingBar",
                spinner_style="bold green",
            )
            self.status.__enter__()

        self.start_time = time.perf_counter()

        if self.show_elapsed:
            # background thread that prints elapsed every second
            def _tick():
                while self.start_time is not None:
                    elapsed = time.perf_counter() - self.start_time
                    sys.stdout.write(f"\r⏱ Elapsed: {elapsed:.1f}s")
                    sys.stdout.flush()
                    time.sleep(1)
            self._ticker = threading.Thread(target=_tick, daemon=True)
            self._ticker.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.perf_counter() - self.start_time
        else:
            duration = 0.0
        Timer.last_duration = duration

        # stop ticker
        self.start_time = None
        if self._ticker and self._ticker.is_alive():
            self._ticker.join(timeout=0.1)
        print()  # newline after last elapsed print

        if self.use_spinner and self.status:
            self.status.__exit__(exc_type, exc_val, exc_tb)

        if self.label:
            self.console.print(
                f"✅ [green]{self.label}[/] done in [yellow]{duration:.2f}s[/]"
            )
