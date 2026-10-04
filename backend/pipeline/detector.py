"""
Layer 2: GLiNER.

GLiNER is NOT a chatbot. It can't write or follow instructions. You give it text +
a list of plain-English labels, and it returns the phrases that match, with exact
character positions and a confidence score. That makes it immune to "prompt
injection" (text inside a note can't change what it does) and it can't invent phrases.
"""
import re

import config

_model = None  # loaded on first use, so the server starts fast and tests can skip it


def _get_model():
    global _model
    if _model is None:
        # Import here so the rest of the app works even before gliner/torch is installed.
        from gliner import GLiNER
        # First run downloads the model from Hugging Face (~few hundred MB) into your cache.
        # After that, set HF_HUB_OFFLINE=1 in .env so it never goes online again.
        _model = GLiNER.from_pretrained(config.GLINER_MODEL)
    return _model


def _chunks(text: str, max_chars: int) -> list[tuple[int, str]]:
    """
    Split text into pieces GLiNER can read (it only sees ~384 tokens at once).
    We split on line breaks so we don't cut a name in half, and remember each
    chunk's starting position so we can map results back to the full note.
    """
    pieces, start, end = [], 0, 0
    for seg_start, seg_end in _segments(text, max_chars):
        if seg_end - start > max_chars and end > start:
            pieces.append((start, text[start:end]))      # close the current chunk
            start = seg_start
        end = seg_end
    if end > start:
        pieces.append((start, text[start:end]))
    return pieces


def _segments(text: str, max_chars: int):
    """
    Yield (start, end) for each line. A line longer than max_chars is cut into smaller pieces,
    at a sentence end if there is one in the second half of the window, else at a space.
    This matters: pdf.py joins each paragraph into one line, and GLiNER silently ignores
    everything past its ~384-token window, so a long line would hide identifiers at its end.
    """
    for m in re.finditer(r"[^\n]*\n|[^\n]+$", text):   # one line at a time (keeps the "\n")
        s, e = m.start(), m.end()
        while e - s > max_chars:
            window = text[s:s + max_chars]
            cut = max(window.rfind(". "), window.rfind("; "), window.rfind("? "), window.rfind("! "))
            if cut < max_chars // 2:
                cut = window.rfind(" ")
            cut = cut + 1 if cut > 0 else max_chars      # keep the punctuation; hard cut if no space at all
            yield s, s + cut
            s += cut
        yield s, e


def detect(text: str) -> list[dict]:
    """Return GLiNER findings as {start, end, type, score, source} (same shape as rules.find)."""
    if not config.USE_GLINER:
        return []

    model = _get_model()
    labels = list(config.GLINER_LABELS)
    spans = []
    for offset, chunk in _chunks(text, config.GLINER_CHUNK_CHARS):
        for e in model.predict_entities(chunk, labels, threshold=config.GLINER_THRESHOLD):
            spans.append({
                "start": e["start"] + offset,              # shift back to full-note positions
                "end": e["end"] + offset,
                "type": config.GLINER_LABELS[e["label"]],  # "occupation" -> "OCCUPATION"
                "score": round(float(e["score"]), 2),
                "source": "gliner",
            })
    return spans
