"""Scrubs desktop app: the Flask backend and the built frontend in one window.

Everything runs on this computer. The only thing that goes over the network is the
pseudonymized text sent to Gemini (backend/gemini_client.py).

  python desktop/launcher.py      run from source (after `npm run build:desktop`)
  Scrubs.exe                      the packaged app (desktop/build.ps1)
  SCRUBS_NO_WINDOW=1              serve only, print the URL (for smoke tests)

This file doesn't change the backend. It imports backend/app.py as-is, points it at
bundled files, and adds two routes that serve the static frontend.
"""

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    BUNDLE = Path(sys._MEIPASS)                       # PyInstaller's unpacked files
    WEB_DIR = BUNDLE / "web"
    DATA_DIR = BUNDLE / "data"
    MODELS_DIR = BUNDLE / "models"
else:
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "backend"))
    WEB_DIR = ROOT / ".next-export"
    DATA_DIR = ROOT / "data"
    MODELS_DIR = None                                 # use GLINER_MODEL from .env and the normal cache

KEYRING_SERVICE = "Scrubs"
KEYRING_USER = "GEMINI_API_KEY"
HEADLESS = os.getenv("SCRUBS_NO_WINDOW") == "1"


def quiet_streams() -> None:
    """A windowed .exe has no console, so stdout/stderr are None and libraries that print
    progress bars crash. Send them nowhere. No log file is written (nothing goes to disk)."""
    if sys.stdout is None or sys.stderr is None:
        devnull = open(os.devnull, "w")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull


def gemini_key() -> str:
    """The key lives in Windows Credential Manager, never in the installer or a file.
    On first run, ask for it once."""
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        import keyring
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
    except Exception:
        keyring = None
    if not key and not HEADLESS:
        key = ask_for_key()
        if key and keyring:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
            except Exception:
                pass
    return key


def ask_for_key() -> str:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except Exception:
        return ""
    root = tk.Tk()
    root.withdraw()
    key = simpledialog.askstring(
        "Scrubs",
        "Paste your Gemini API key.\n\nIt is saved in Windows Credential Manager on this computer.\n"
        "Leave it blank to use Scrubs without the chatbot.",
        show="*",
        parent=root,
    )
    root.destroy()
    return (key or "").strip()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def configure_env(port: int) -> None:
    """Must run before the backend is imported: backend/config.py reads these at import time."""
    os.environ.setdefault("LEXICON_SOURCE", "csv")    # the BC lexicon ships with the app
    os.environ.setdefault("USE_GLINER", "1")
    os.environ["HF_HUB_OFFLINE"] = "1"                # never download models at runtime
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    if MODELS_DIR:
        # A self-contained GLiNER folder (weights + tokenizer), made by desktop/prepare_models.py.
        os.environ["GLINER_MODEL"] = str(MODELS_DIR / "gliner_medium")
    os.environ["FRONTEND_ORIGINS"] = f"http://127.0.0.1:{port}"
    os.environ["GEMINI_API_KEY"] = gemini_key()


def build_app():
    from flask import abort, send_from_directory

    import app as backend                              # backend/app.py
    from pipeline import lexicon

    lexicon.SEED_CSV = DATA_DIR / "lexicon_seed.csv"  # the bundled copy
    flask_app = backend.app

    # The API routes (/documents, /chat, ...) are more specific, so Flask matches them first.
    @flask_app.get("/")
    def desktop_index():
        return send_from_directory(WEB_DIR, "index.html")

    @flask_app.get("/<path:path>")
    def desktop_static(path):
        if (WEB_DIR / path).is_file():
            return send_from_directory(WEB_DIR, path)
        abort(404)

    return flask_app


def warm_up() -> None:
    """Load GLiNER in the background so the first scan isn't slow."""
    try:
        import pipeline
        pipeline.analyze("Warm up.")
    except Exception:
        pass


def wait_until_up(url: str, seconds: float = 120) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=2):
                return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> None:
    quiet_streams()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    configure_env(port)
    flask_app = build_app()

    from waitress import serve

    threading.Thread(target=lambda: serve(flask_app, host="127.0.0.1", port=port, threads=8), daemon=True).start()
    threading.Thread(target=warm_up, daemon=True).start()
    wait_until_up(url)

    if HEADLESS:
        print(url, flush=True)
        threading.Event().wait()

    try:
        import webview
        webview.create_window("Scrubs", url, width=1400, height=900, min_size=(900, 600))
        webview.start()                                # returns when the window closes
    except Exception:
        # No embedded browser available: use the default one and keep serving until killed.
        import webbrowser
        webbrowser.open(url)
        threading.Event().wait()


if __name__ == "__main__":
    main()
