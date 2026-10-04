"""
The whole detection pipeline in one call:

    raw text -> rules (Presidio) + GLiNER + BC lexicon -> merge -> risk levels
"""
from collections import Counter

from . import detector, lexicon, merge, risk, rules


def analyze(text: str) -> dict:
    rule_spans = rules.find(text)        # layer 1: structured IDs (PHN, phone, dates...) + names
    model_spans = detector.detect(text)  # layer 2: names + subtle identifiers (occupation, town...)
    lex_spans = lexicon.find(text)       # layer 3: known BC towns/facilities/occupations (list from TiDB, matched here)
    spans = merge.merge(text, rule_spans, model_spans, lex_spans)
    spans, overall = risk.score(spans)
    return {"spans": spans, "risk": overall}


def summary(spans: list[dict]) -> str:
    """Counts only, e.g. '2 PERSON, 1 PHN'. This is the ONLY thing we ever log."""
    return ", ".join(f"{n} {t}" for t, n in Counter(s["type"] for s in spans).most_common())
