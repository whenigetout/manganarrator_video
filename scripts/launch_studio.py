"""Launch one local server containing both FastAPI and the built React application."""
import argparse
import json
import os
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


def available_port(preferred):
    for port in range(preferred, preferred + 30):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free studio port found")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
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
        print("Audio Studio: " + url, flush=True)
        if not args.no_browser:
            webbrowser.open(url + "#publishingToken=" + token)

    previous = {}
    if state_file.exists():
        try:
            previous = json.loads(state_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    if isinstance(previous.get("port"), int) and 1024 <= previous["port"] <= 65535 and alive(previous["port"]):
        open_studio(previous["port"])
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
        print("Startup is taking longer than expected. Check the backend messages above.", flush=True)

    print("Starting backend and React studio. Keep this window open; Ctrl+C stops the server.", flush=True)
    print("Google redirect URI: " + os.environ["PUBLISHING_REDIRECT_URI"], flush=True)
    threading.Thread(target=ready, daemon=True).start()
    import uvicorn
    uvicorn.run("video_server:app", host="127.0.0.1", port=port, access_log=False)


if __name__ == "__main__":
    main()
