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

    # An unexpected error shows its type and where it happened, never values or note text,
    # so a 500 in the desktop app can be traced without a console.
    from werkzeug.exceptions import HTTPException

    @flask_app.errorhandler(Exception)
    def desktop_error(e):
        if isinstance(e, HTTPException):
            return e
        import traceback
        last = traceback.extract_tb(e.__traceback__)[-1] if e.__traceback__ else None
        where = f" in {Path(last.filename).name} line {last.lineno}" if last else ""
        return {"detail": f"Something went wrong ({type(e).__name__}{where}). Try again."}, 500

    return flask_app


def warm_up() -> None:
    """Load GLiNER now so the first scan isn't slow and never races the model load."""
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


_mutex = None  # held for the life of the process


def already_running() -> bool:
    """One copy at a time. Starting takes a while, and people click the icon again."""
    global _mutex
    if sys.platform != "win32":
        return False
    import ctypes
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ScrubsDesktopApp")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def tell(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Scrubs", message, parent=root)
        root.destroy()
    except Exception:
        pass


# Shown the moment the window opens, while the detection models load (up to a minute).
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;font-family:"Segoe UI",system-ui,sans-serif;background:#f0f2f4;color:#1b1b1b}}
header{{background:#0b2f4e;color:#fff;border-bottom:4px solid #00788a;padding:14px 32px;font-size:22px;font-weight:700}}
main{{max-width:560px;margin:96px auto;text-align:center}}
h1{{font-size:20px;color:#0b2f4e;margin:20px 0 8px}} p{{color:#565c65;margin:0}}
.spin{{width:36px;height:36px;margin:0 auto;border:3px solid #d6dbe1;border-top-color:#205493;border-radius:50%;animation:s .8s linear infinite}}
@keyframes s{{to{{transform:rotate(360deg)}}}}
</style></head><body><header>Scrubs</header><main>{body}</main></body></html>"""
LOADING = PAGE.format(body='<div class="spin"></div><h1>Starting Scrubs</h1>'
                           "<p>Loading the detection models on this computer. This can take up to a minute.</p>")


def failed_page(reason: str) -> str:
    import html
    return PAGE.format(body=f"<h1>Scrubs could not start</h1><p>{html.escape(reason)}</p><p>Close this window and open Scrubs again.</p>")


def start_backend(port: int) -> str:
    """Import the backend and serve it. Returns the URL. Slow: loads torch, spaCy, Presidio."""
    url = f"http://127.0.0.1:{port}"
    flask_app = build_app()
    from waitress import serve

    threading.Thread(target=lambda: serve(flask_app, host="127.0.0.1", port=port, threads=8), daemon=True).start()
    if not wait_until_up(url):
        raise RuntimeError("The local server did not start.")
    # Load GLiNER before showing the app. If a scan arrives while the model is still loading,
    # two threads load it at once and the scan can fail with a 500.
    warm_up()
    return url


def main() -> None:
    quiet_streams()
    if already_running():
        tell("Scrubs is already open. It can take up to a minute to appear.")
        return
    port = free_port()
    configure_env(port)

    if HEADLESS:
        print(start_backend(port), flush=True)
        threading.Event().wait()

    try:
        import webview
    except Exception:
        webview = None

    if webview is None:
        # No embedded browser available: use the default one and keep serving until closed.
        import webbrowser
        webbrowser.open(start_backend(port))
        threading.Event().wait()
        return

    window = webview.create_window("Scrubs", html=LOADING, width=1400, height=900, min_size=(900, 600))

    def boot():
        try:
            window.load_url(start_backend(port))
        except Exception as e:
            window.load_html(failed_page(f"{type(e).__name__}: {e}"))

    webview.start(boot)                                # returns when the window closes


if __name__ == "__main__":
    main()
