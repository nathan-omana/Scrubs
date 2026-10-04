"""PDF text extraction with pdfplumber.

Text-based PDFs only. Scanned PDFs (no text layer) are rejected; OCR is a stretch goal.
The extracted text becomes `original_text`, and every flag's start_idx/end_idx points
into it, so the cleanup here must happen before detection, never after.
"""

import io
import re
import textwrap

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 30
# Fewer characters than this across the whole file means there is no usable text layer.
MIN_TEXT_CHARS = 20


class PdfError(ValueError):
    """The upload can't be turned into text. The message is safe to show the user."""


class ScannedPdfError(PdfError):
    pass


_CHAR_FIXES = {
    " ": " ",  # non-breaking space
    "­": "",  # soft hyphen
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}
_SENTENCE_END = re.compile(r"[.:;!?)\]]$")
# Lines that start a new item even when the line before looks unfinished.
_NEW_ITEM = re.compile(r"^\s*([-*•]|\d+[.)]\s|[A-Z][\w /#()]{0,30}:)")
# In layout text, three or more spaces is a visual gap: a new column or a table cell.
_COLUMN_GAP = re.compile(r"(?<=\S) {3,}(?=\S)")
# Layout grid step, as this quantile of the page's character widths. Wide enough that capitals
# don't spill extra spaces into a word gap, narrow enough that small print keeps its column gaps.
_GRID_QUANTILE = 0.9
_INDENT = re.compile(r"^ +(?=\S)")


def _fix_chars(text: str) -> str:
    for bad, good in _CHAR_FIXES.items():
        text = text.replace(bad, good)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _page_text(page) -> str:
    """Text of one page with side-by-side columns kept apart.

    Layout mode places each word on a character grid by its position on the page. The grid
    step comes from the page's own character widths, so a gap between columns stays a gap even
    in small print (the 7.25pt default squeezes it to one space). The tolerance scales with font
    size too: the fixed 3pt default glues words together in small print that draws gaps
    instead of space characters ("FelixKongyuy")."""
    widths = sorted(c["width"] for c in page.chars if c["text"].strip())
    if not widths:
        return ""
    grid = widths[int(_GRID_QUANTILE * (len(widths) - 1))]
    text = page.extract_text(x_tolerance_ratio=0.15, layout=True, x_density=grid)
    # Layout mode pads every line to the page width and adds blank lines for the margins.
    lines = [line.rstrip() for line in (text or "").split("\n")]
    return textwrap.dedent("\n".join(lines)).strip("\n")


def _reflow(page_text: str) -> str:
    """Join lines that pdfplumber split mid-sentence, so phrases like
    "the small red house beside the Hope community hall" stay on one line for detection.
    A line is joined to the one before when that line doesn't end a sentence and either
    the new line starts lowercase or the line before ran close to the full page width
    (a wrapped paragraph). List items, "Label: value" lines and lines split into columns
    always start a new line. Each column gap then becomes one tab."""
    lines = [line.rstrip() for line in page_text.split("\n")]
    wrap_width = 0.75 * max((len(line) for line in lines), default=0)
    out: list[str] = []
    prev_line = ""  # the previous physical line, before any joining
    for line in lines:
        prev = out[-1] if out else ""
        wrapped = line[:1].islower() or len(prev_line) >= wrap_width
        in_columns = _COLUMN_GAP.search(prev) or _COLUMN_GAP.search(line.strip())
        if (
            prev
            and line.strip()
            and wrapped
            and not in_columns
            and not _SENTENCE_END.search(prev)
            and not _NEW_ITEM.match(line)
        ):
            if prev.endswith("-") and not prev.endswith(" -"):
                out[-1] = prev + line.lstrip()  # "follow-" + "up" -> "follow-up"
            else:
                out[-1] = prev + " " + line.lstrip()
        else:
            out.append(line)
        prev_line = line
    # A tab per gap keeps cells apart for the reader and for detection, so a flagged span
    # never runs from one column into the next ("Invoice Number VANCOUVER").
    return "\n".join(_cells(line) for line in out)


def _cells(line: str) -> str:
    """Column gaps and deep indents become one tab each; a slight indent is grid noise."""
    line = _COLUMN_GAP.sub("\t", line)
    return _INDENT.sub(lambda m: "\t" if len(m.group()) >= 3 else "", line)


def clean_text(pages: list[str]) -> str:
    text = "\n\n".join(_reflow(_fix_chars(p)).strip() for p in pages if p and p.strip())
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text(data: bytes) -> tuple[str, int]:
    """Returns (cleaned text, page count). Raises PdfError with a user-facing message."""
    if len(data) > MAX_BYTES:
        raise PdfError(f"PDF is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not data.lstrip()[:5] == b"%PDF-":
        raise PdfError("This file is not a PDF.")

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            if page_count > MAX_PAGES:
                raise PdfError(f"PDF has {page_count} pages. The limit is {MAX_PAGES}.")
            pages = [_page_text(page) for page in pdf.pages]
    except PdfError:
        raise
    except PDFSyntaxError as exc:
        raise PdfError("This PDF is damaged and can't be read.") from exc
    except Exception as exc:  # pdfminer raises several types, e.g. for password-protected files
        name = type(exc).__name__
        if "Password" in name or "Encrypt" in name:
            raise PdfError("This PDF is password protected. Remove the password and try again.") from exc
        raise PdfError("This PDF can't be read.") from exc

    text = clean_text(pages)
    if len(text) < MIN_TEXT_CHARS:
        raise ScannedPdfError(
            "No text found in this PDF. It may be a scanned image, which isn't supported yet. "
            "Paste the note text instead."
        )
    return text, page_count
