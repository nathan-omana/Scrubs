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
    for m in re.finditer(r"[^\n]*\n|[^\n]+$", text):   # one line at a time (keeps the "\n")
        if m.end() - start > max_chars and end > start:
            pieces.append((start, text[start:end]))      # close the current chunk
            start = m.start()
        end = m.end()
    if end > start:
        pieces.append((start, text[start:end]))
    return pieces
    # Note: a single line longer than max_chars still becomes one chunk.
    # GLiNER will truncate it. Fine for now; split on sentences later if notes have huge lines.


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
