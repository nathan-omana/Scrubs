"""Saves GLiNER (weights + tokenizer) to desktop/build/models/gliner_medium so the app can
load it with no Hugging Face cache and no internet.

Run once before building (needs the model downloaded once, or internet):
    backend/.venv/Scripts/python desktop/prepare_models.py
"""

import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "build" / "models" / "gliner_medium"
MODEL = os.getenv("GLINER_MODEL", "urchade/gliner_medium-v2.1")


def main() -> int:
    if (OUT / "gliner_config.json").exists():
        print(f"Already prepared: {OUT}")
        return 0
    from gliner import GLiNER

    model = GLiNER.from_pretrained(MODEL)
    OUT.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUT))
    print(f"Saved {MODEL} to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
