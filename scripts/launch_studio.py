"""Launch one local server containing both FastAPI and the built React application.

The studio is a single process: FastAPI serves the API and the built React app on
/studio/. Everything printed by the launcher, Uvicorn and the application is also
written to local_tmp/logs/studio-<date>.log so the console can be reviewed later.
"""
import argparse
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

LOG_DIRECTORY = ROOT / "local_tmp" / "logs"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
STAMPED = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]")


def log_path():
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    return LOG_DIRECTORY / time.strftime("studio-%Y%m%d.log")


class ConsoleLog:
    """Console stream that also appends plain text to the studio log file."""

    def __init__(self, stream, handle):
        self._stream = stream
        self._handle = handle
        self._buffer = ""

    def write(self, text):
        self._stream.write(text)
        if text:
            try:
                self._buffer += ANSI_ESCAPE.sub("", text)
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    if not STAMPED.match(line):
                        line = time.strftime("[%H:%M:%S] ") + line
                    self._handle.write(line + "\n")
                self._handle.flush()
            except (OSError, ValueError):
                pass
        return len(text)

    def flush(self):
        self._stream.flush()
        try:
            if self._buffer:
                self._handle.write(time.strftime("[%H:%M:%S] ") + self._buffer.rstrip("\r") + "\n")
                self._buffer = ""
            self._handle.flush()
        except (OSError, ValueError):
            pass

    def isatty(self):
        return self._stream.isatty()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_console_log(path):
    handle = open(path, "a", encoding="utf-8", errors="replace")
    sys.stdout = ConsoleLog(sys.stdout, handle)
    sys.stderr = ConsoleLog(sys.stderr, handle)
    return handle


def say(message):
    print(time.strftime("[%H:%M:%S] ") + message, flush=True)


def available_port(preferred):
    for port in range(preferred, preferred + 30):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free studio port found")


def hold_window():
    """Keep the launcher window readable when the server runs in another window."""
    try:
        if not (sys.stdin and sys.stdin.isatty()):
            return
        input("Press Enter to close this window. The running studio keeps working.")
    except (EOFError, KeyboardInterrupt):
        pass


def ensure_audio_dependencies():
    """Install the audio renderer requirements when numpy/OpenCV are missing."""
    import importlib.util
    import subprocess

    missing = [name for name in ("numpy", "cv2") if importlib.util.find_spec(name) is None]
    if not missing:
        return
    say("Missing audio dependencies: " + ", ".join(missing) + ".")
    say("Installing requirements-audio.txt into " + sys.executable + " ...")
    try:
        code = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements-audio.txt")]).returncode
    except OSError as error:
        say("Could not run pip: " + str(error))
        code = 1
    still_missing = [name for name in missing if importlib.util.find_spec(name) is None]
    if code != 0 or still_missing:
        say("WARNING: live frames and rendered videos fail until this install succeeds. Run:")
        say('  "' + sys.executable + '" -m pip install -r requirements-audio.txt')
    else:
        say("Audio dependencies installed.")


def run(args, path):
    say("Full studio log: " + str(path))
    ensure_audio_dependencies()
    from app.publishing.settings import Settings
    settings = Settings()
    token = settings.owner_key()
    state_file = settings.directory / "launcher.json"

    def alive(port):
        request = urllib.request.Request(f"http://127.0.0.1:{port}/video/publishing/configuration",
                                         headers={"Authorization": "Bearer " + token, "X-Publishing-Client": "studio"})
        try:
            with urllib.request.urlopen(request, timeout=2) as result:
                return result.status == 200
        except Exception:
            return False

    def open_studio(port):
        url = f"http://127.0.0.1:{port}/studio/"
        say("Audio Studio: " + url)
        say("This single process serves the backend API and the built React app.")
        if not args.no_browser:
            webbrowser.open(url + "#publishingToken=" + token)

    previous = {}
    if state_file.exists():
        try:
            previous = json.loads(state_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    if isinstance(previous.get("port"), int) and 1024 <= previous["port"] <= 65535 and alive(previous["port"]):
        say(f"A studio is already answering on port {previous['port']}; reusing it instead of starting a second one.")
        open_studio(previous["port"])
        say("Its console is the window that started it; logs are in the file printed above.")
        hold_window()
        return
    port = available_port(int(os.environ.get("STUDIO_PORT", previous.get("port", 8084))))
    os.environ["PUBLISHING_ENABLED"] = "1"
    os.environ["PUBLISHING_ORIGINS"] = f"http://127.0.0.1:{port},http://localhost:{port},http://127.0.0.1:5173,http://localhost:5173"
    os.environ["PUBLISHING_REDIRECT_URI"] = f"http://127.0.0.1:{port}/video/publishing/oauth/callback"
    state_file.write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")

    def ready():
        for _ in range(120):
            if alive(port):
                open_studio(port)
                return
            time.sleep(1)
        say("Startup is taking longer than expected. Check the backend messages above.")

    say(f"Starting the backend and React studio on port {port}. Keep this window open; Ctrl+C stops the server.")
    say("Google redirect URI: " + os.environ["PUBLISHING_REDIRECT_URI"])
    threading.Thread(target=ready, daemon=True).start()
    import uvicorn
    uvicorn.run("video_server:app", host="127.0.0.1", port=port, access_log=args.access_log)
    say("Studio server stopped.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--access-log", action="store_true", help="Log every HTTP request; useful while developing.")
    args = parser.parse_args()
    path = log_path()
    handle = install_console_log(path)
    say("=== MangaNarrator Studio launch " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===")
    try:
        run(args, path)
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        try:
            print("Studio log saved to " + str(path))
        except (OSError, ValueError):
            pass
        handle.close()


if __name__ == "__main__":
    main()
