"""
File -> plain text, entirely in memory. Nothing is written to disk.
"""
import io

import pdfplumber
from docx import Document


def extract_text(filename: str, data: bytes) -> str:
    """Turn uploaded file bytes into text. Supports .txt, .pdf, .docx."""
    name = (filename or "").lower()

    if name.endswith(".pdf"):
        # pdfplumber can read from a BytesIO, so the PDF never touches the disk.
        # Note: scanned PDFs (images) have no text layer and will come back empty.
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)

    # Default: treat as plain text.
    return data.decode("utf-8", errors="replace")
