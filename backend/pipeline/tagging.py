"""
Tagging and restoring. No AI here, just find-and-replace.

In the real app this logic lives in the browser (so the mapping never leaves the screen).
It's in Python too so we can test the whole flow from the command line, and so the
frontend team has a reference to copy.
"""
import re


def tag_text(text: str, spans: list[dict], remove_ids: set[int]) -> tuple[str, dict]:
    """
    Replace the chosen spans with tags like [PERSON_1].
    The same value always gets the same tag ("Jane Doe" twice -> [PERSON_1] twice).
    Returns (tagged_text, mapping) where mapping = {"[PERSON_1]": "Jane Doe", ...}.
    """
    chosen = [s for s in spans if s["id"] in remove_ids]

    # SAFETY: if "Tofino" was flagged once, also catch every OTHER place "Tofino" appears,
    # even if the detectors missed that occurrence. Otherwise one miss = one leak.
    chosen = _add_repeats(text, chosen)
    chosen.sort(key=lambda s: s["start"])

    # 1) Decide the tag for each span, in reading order, so numbering looks natural.
    counters: dict[str, int] = {}
    value_to_tag: dict[tuple[str, str], str] = {}
    tags = []
    for s in chosen:
        value = text[s["start"]:s["end"]]
        key = (s["type"], value.strip().lower())       # case-insensitive match
        if key not in value_to_tag:
            counters[s["type"]] = counters.get(s["type"], 0) + 1
            value_to_tag[key] = f"[{s['type']}_{counters[s['type']]}]"
        tags.append((s, value_to_tag[key], value))

    # 2) Replace from the END of the text backwards, so earlier positions stay correct.
    out = text
    for s, tag, _ in sorted(tags, key=lambda t: t[0]["start"], reverse=True):
        out = out[:s["start"]] + tag + out[s["end"]:]

    mapping = {tag: value for _, tag, value in tags}
    return out, mapping


def _add_repeats(text: str, chosen: list[dict]) -> list[dict]:
    """Find other occurrences of each chosen value (whole words, any case) and add them."""
    taken = [(s["start"], s["end"]) for s in chosen]
    extra = []
    for s in chosen:
        value = text[s["start"]:s["end"]].strip()
        if len(value) < 3:                       # skip tiny values like "Al" to avoid nonsense matches
            continue
        # (?<!\w) / (?!\w) instead of \b: \b needs a letter or digit at the edge, so a value
        # that starts with "(" like "(250) 555-0142" would never match and its repeats would leak.
        for m in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text, re.IGNORECASE):
            overlaps = any(m.start() < e and m.end() > b for b, e in taken)
            if not overlaps:
                extra.append({**s, "start": m.start(), "end": m.end()})
                taken.append((m.start(), m.end()))
    return chosen + extra


# Gemini sometimes rewrites tags slightly: "[PERSON_1]", "PERSON_1", "[Person 1]".
# Bracketed forms may use a space and inner padding; bare forms need the underscore, so ordinary
# text like "Type 2" is never touched. The surrounding spaces are never consumed.
_TAG_LIKE = re.compile(r"\[\s*([A-Za-z]+)[ _](\d+)\s*\]|\b([A-Za-z]+)_(\d+)\b")


def restore(answer: str, mapping: dict) -> str:
    """Swap tags in Gemini's answer back to the real values. Unknown tags are left alone."""
    def swap(m: re.Match) -> str:
        name, number = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        tag = f"[{name.upper()}_{number}]"
        return mapping.get(tag, m.group(0))
    return _TAG_LIKE.sub(swap, answer)


def tag_question(question: str, mapping: dict) -> str:
    """Replace any real values the clinician typed (e.g. the patient's name) with their tags."""
    # Longest values first, so "Jane Doe" is replaced before "Jane".
    # Whole words only: a masked age "74" must not turn "740 mg" into "[AGE_1]0 mg".
    for tag, value in sorted(mapping.items(), key=lambda kv: -len(kv[1])):
        question = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", lambda _m, t=tag: t,
                          question, flags=re.IGNORECASE)
    return question
