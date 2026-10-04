"""Builds small text PDFs with no extra dependencies, for tests and synthetic samples.

Each page is a list of lines; long lines are wrapped like a word processor would.
Text must be Latin-1 (Helvetica with WinAnsi encoding).
With spaceless=True, words are placed with gaps instead of space characters, the way many
invoice and form generators write them. A run of three or more spaces then becomes a wide gap,
like the space between two columns.
"""

import re
import textwrap

PAGE_W, PAGE_H = 612, 792  # US Letter, points
MARGIN = 72
FONT_SIZE = 11
LEADING = 15
WRAP_CHARS = 90
SPACE_WIDTH = 278  # Helvetica space, in thousandths of the font size
COLUMN_GAP_WIDTH = 20 * SPACE_WIDTH


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _show(line: str, spaceless: bool) -> str:
    if not spaceless:
        return f"({_escape(line)}) Tj"
    parts = []
    for piece in re.split(r"( +)", line.strip()):
        if piece.startswith(" "):
            parts.append(f"-{COLUMN_GAP_WIDTH if len(piece) >= 3 else SPACE_WIDTH}")
        else:
            parts.append(f"({_escape(piece)})")
    return "[" + " ".join(parts) + "] TJ"


def _content_stream(lines: list[str], font_size: float, spaceless: bool) -> bytes:
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, WRAP_CHARS) or [""])
    ops = [f"BT /F1 {font_size} Tf {LEADING} TL {MARGIN} {PAGE_H - MARGIN} Td"]
    ops += [f"{_show(line, spaceless)} T*" for line in wrapped]
    ops.append("ET")
    return "\n".join(ops).encode("latin-1")


def build_pdf(pages: list[list[str]], font_size: float = FONT_SIZE, spaceless: bool = False) -> bytes:
    """pages: one list of text lines per page. An empty list gives a page with no text."""
    objects: list[bytes] = []  # object n is objects[n - 1]

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # filled in once the page tree exists
    pages_obj = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    kids = []
    for lines in pages:
        stream = _content_stream(lines, font_size, spaceless) if lines else b""
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_obj, PAGE_W, PAGE_H, font, content)
            )
        )

    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj
    objects[pages_obj - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(out)
