# PyInstaller spec for the Scrubs desktop app. Build with desktop/build.ps1, not by hand.
# Output: desktop/dist/Scrubs/Scrubs.exe (a folder, not one file: it starts much faster).
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"
CONSOLE = os.getenv("SCRUBS_CONSOLE") == "1"   # 1 = show a console window, for debugging a build

datas = [
    (str(ROOT / ".next-export"), "web"),
    (str(ROOT / "data" / "lexicon_seed.csv"), "data"),
    (str(ROOT / "desktop" / "build" / "models" / "gliner_medium"), "models/gliner_medium"),
]
binaries = []
# The backend modules, imported by name from backend/ (pathex below).
hiddenimports = [
    "app", "config", "gemini_client", "audit",
    "pipeline", "pipeline.detector", "pipeline.extract", "pipeline.lexicon", "pipeline.merge",
    "pipeline.pdf", "pipeline.risk", "pipeline.rules", "pipeline.tagging",
    "waitress", "keyring.backends.Windows",
]

# Packages that load data files or plugins at runtime.
for pkg in ["presidio_analyzer", "spacy", "en_core_web_sm", "thinc", "gliner", "tldextract",
            "pdfplumber", "pdfminer", "docx", "google.genai", "webview", "transformers", "tokenizers"]:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Libraries that check their own or their dependencies' installed versions.
for dist in ["transformers", "tokenizers", "huggingface-hub", "safetensors", "torch", "tqdm", "regex",
             "requests", "packaging", "filelock", "numpy", "pyyaml", "gliner", "spacy", "presidio-analyzer",
             "google-genai"]:
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "IPython", "jupyter", "notebook", "pytest", "tensorboard"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Scrubs",
    console=CONSOLE,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Scrubs", upx=False)
