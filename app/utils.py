from pathlib import Path
import time
from rich.console import Console
import sys
import threading

import traceback

def log_exception(context: str = "Unhandled exception", label: str = "💀"):
    print(f"\n{label} {context}:")
    traceback.print_exc()

def ensure_folder(path: Path):
    path.mkdir(parents=True, exist_ok=True)

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
