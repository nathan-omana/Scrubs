"""
File -> plain text, entirely in memory. Nothing is written to disk.
"""
import io

from docx import Document

from . import pdf
from .pdf import PdfError, ScannedPdfError  # noqa: F401  (re-exported so app.py can catch them)


def extract_text(filename: str, data: bytes) -> str:
    """Turn uploaded file bytes into text. Supports .txt, .pdf, .docx."""
    name = (filename or "").lower()

    if name.endswith(".pdf"):
        # pdf.py reads from a BytesIO, so the PDF never touches the disk. It also rejoins
        # wrapped lines, keeps columns apart, and raises PdfError / ScannedPdfError with a
        # message that's safe to show the user (scanned PDFs have no text layer).
        text, _pages = pdf.extract_text(data)
        return text

    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)

    # Default: treat as plain text.
    return data.decode("utf-8", errors="replace")
