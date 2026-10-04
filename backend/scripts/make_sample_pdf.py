"""Writes the synthetic demo note to data/samples/demo_visit_note.pdf.

Run from backend/:  .venv/Scripts/python -m scripts.make_sample_pdf
"""

from pathlib import Path

from tests.pdf_factory import build_pdf
from tests.samples import DEMO_PAGES

OUT = Path(__file__).resolve().parents[2] / "data" / "samples" / "demo_visit_note.pdf"

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_pdf(DEMO_PAGES))
    print(f"Wrote {OUT}")
