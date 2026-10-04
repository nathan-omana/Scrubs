"""
The whole detection pipeline in one call:

    raw text -> rules (Presidio) + GLiNER + BC lexicon -> merge -> tiers and reasons (flags)
"""
from collections import Counter

from . import detector, lexicon, merge, risk, rules


def analyze(text: str) -> list[dict]:
    """
    Returns flags in reading order (F1, F2...), each with start_idx, end_idx, text, label, tier,
    reason, masked, locked, source, plus internal `type` and `found_by`. No pseudonyms yet.
    """
    rule_spans = rules.find(text)        # layer 1: structured IDs (PHN, phone, dates...) + names
    model_spans = detector.detect(text)  # layer 2: names + subtle identifiers (occupation, town...)
    lex_spans = lexicon.find(text)       # layer 3: known BC towns/facilities/occupations (list from TiDB, matched here)
    spans = merge.merge(text, rule_spans, model_spans, lex_spans)
    return risk.to_flags(text, spans)


def summary(flags: list[dict]) -> str:
    """Counts only, e.g. '2 Person, 1 PHN'. This is the ONLY thing we ever log about a document."""
    return ", ".join(f"{n} {label}" for label, n in Counter(f["label"] for f in flags).most_common())
