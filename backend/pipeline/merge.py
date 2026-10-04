"""
Combine the findings from rules (Presidio), GLiNER and the BC lexicon into one clean list.

Policy: keep EVERYTHING any layer found (a miss is a leak; an extra flag is one click),
except words on the never-redact list. When two findings overlap, join them into one span.
"""
import re

import config


def _is_medical_term(span_text: str) -> bool:
    # "Parkinson's" / "Foley" etc. look like names to a model, but they're clinical terms.
    words = re.findall(r"[\w']+", span_text.lower())
    return len(words) == 1 and words[0] in config.NEVER_REDACT


def _fully_covered(text: str, span: dict, others: list[dict]) -> bool:
    """True if every word inside `span` sits inside at least one of `others`."""
    for w in re.finditer(r"\S+", text[span["start"]:span["end"]]):
        ws, we = span["start"] + w.start(), span["start"] + w.end()
        if not any(o["start"] <= ws and we <= o["end"] for o in others):
            return False
    return bool(others)


def _overlaps(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def _priority(span: dict) -> int:
    if span["source"] == "rules" and span["type"] in config.STRUCTURED_TYPES:
        return 3   # pattern/checksum match
    if span["source"] == "gliner":
        return 2   # specialist model, understands context
    if span["source"] == "lexicon":
        return 1   # exact match against our BC list, but blind to context
    return 0       # Presidio's general-purpose PERSON guess


def merge(text: str, rule_spans: list[dict], model_spans: list[dict],
          lexicon_spans: list[dict] | None = None) -> list[dict]:
    lexicon_spans = lexicon_spans or []

    # Ambiguous lexicon hits ("Hope", "Golden", "Nelson", "judge") are also everyday words or
    # names, so on their own they'd flag "Hope she improves". Keep them ONLY if GLiNER, which
    # understands context, flagged the same place too. Non-ambiguous hits ("Tofino",
    # "bush pilot") are always kept: that's the lexicon's whole job.
    lexicon_spans = [l for l in lexicon_spans
                     if not l.get("ambiguous") or any(_overlaps(l, g) for g in model_spans)]

    spans = [s for s in rule_spans + model_spans + lexicon_spans
             if not _is_medical_term(text[s["start"]:s["end"]])]

    # If Presidio's spaCy guessed a PERSON (e.g. "Daughter Claire") and GLiNER already covers
    # every word of it with finer spans ("Daughter" = RELATION, "Claire" = PERSON), keep GLiNER's
    # version so the clinician sees two precise flags instead of one blurry one.
    # If GLiNER missed any word, we keep Presidio's span: a miss is a leak.
    # Same idea for the lexicon: spaCy's "bush" is dropped when the lexicon matched "bush pilot".
    precise = [s for s in spans if s["source"] in ("gliner", "lexicon")]
    spans = [s for s in spans
             if not (s["source"] == "rules" and s["type"] == "PERSON"
                     and _fully_covered(text, s, precise))]

    # Sort by start position; if two start together, the longer one comes first.
    spans.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))

    merged: list[dict] = []
    for s in spans:
        if merged and s["start"] < merged[-1]["end"]:          # overlaps the previous span
            m = merged[-1]
            m["end"] = max(m["end"], s["end"])                 # grow to cover both
            # Who decides the TYPE of the combined span?
            #   1. A structured rule (PHN checksum, phone pattern...) beats any guess.
            #   2. Then GLiNER (context-aware specialist).
            #   3. Then the lexicon (exact BC list match).
            #   4. Then Presidio's spaCy PERSON guess. Ties: higher score wins.
            if _priority(s) > _priority(m) or (_priority(s) == _priority(m) and s["score"] > m["score"]):
                m.update(type=s["type"], source=s["source"], score=s["score"])
            m["found_by"] = sorted(set(m["found_by"]) | {s["source"]})
        else:
            merged.append({**s, "found_by": [s["source"]]})

    # Give each span an id (the frontend uses it for approve/reject) and its text.
    for i, m in enumerate(merged):
        m["id"] = i
        m["text"] = text[m["start"]:m["end"]]
        m.pop("ambiguous", None)                               # internal detail, not for the UI
    return merged
