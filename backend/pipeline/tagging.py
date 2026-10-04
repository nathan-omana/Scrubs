"""
Pseudonyms, pseudonymizing and restoring (CLAUDE.md section 8). No AI here, just find-and-replace.

The browser re-identifies Gemini's answer with the mapping from GET /documents/{id}/mapping.
restore() is the same logic in Python, for demo.py and the tests, and as a reference for the frontend.
"""
import re

import config

# Titles are stripped before lookup, so "Mrs. Park" and "Park" can share one pseudonym later.
_TITLES = re.compile(r"^(mr|mrs|ms|miss|mx|dr|doctor|prof)\.?\s+", re.IGNORECASE)


def normalize(value: str) -> str:
    """Lowercase, strip a leading title, collapse spaces: "Dr.  Raj Patel" -> "raj patel"."""
    v = re.sub(r"\s+", " ", value.strip().lower())
    return _TITLES.sub("", v)


class Pseudonyms:
    """
    Hands out [PREFIX_NN] pseudonyms. The same real value always gets the same pseudonym for as
    long as this object lives (the server process), across every document. Kept in memory only.
    """

    def __init__(self):
        self._by_value: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}

    def get(self, prefix: str, value: str) -> str:
        key = (prefix, normalize(value))
        if key not in self._by_value:
            self._counts[prefix] = self._counts.get(prefix, 0) + 1
            self._by_value[key] = f"[{prefix}_{self._counts[prefix]:02d}]"
        return self._by_value[key]


def pseudonymize(text: str, flags: list[dict]) -> str:
    """
    Replace every masked flag with its pseudonym. Unmasked flags stay as original text.

    SAFETY: if "Tofino" is masked once, every OTHER whole-word occurrence of "Tofino" (any case)
    is replaced too, even where no detector flagged it. Otherwise one miss = one leak.
    """
    masked = [f for f in flags if f["masked"]]
    edits = [(f["start_idx"], f["end_idx"], f["pseudonym"]) for f in masked]
    taken = [(s, e) for s, e, _ in edits]
    for f in masked:
        value = f["text"].strip()
        if len(value) < config.MIN_REPEAT_CHARS:  # tiny values like "Al" or "2": flagged spot only
            continue
        # (?<!\w) / (?!\w) instead of \b: \b needs a letter or digit at the edge, so a value
        # that starts with "(" like "(250) 555-0142" would never match and its repeats would leak.
        for m in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text, re.IGNORECASE):
            if not any(m.start() < e and m.end() > s for s, e in taken):
                edits.append((m.start(), m.end(), f["pseudonym"]))
                taken.append((m.start(), m.end()))

    # Replace from the END backwards, so earlier positions stay correct.
    out = text
    for s, e, pseudonym in sorted(edits, reverse=True):
        out = out[:s] + pseudonym + out[e:]
    return out


def mapping_of(flags: list[dict]) -> dict[str, str]:
    """Pseudonym -> real value, for masked flags only (unmasked items never get into the mapping)."""
    out: dict[str, str] = {}
    for f in flags:
        if f["masked"]:
            out.setdefault(f["pseudonym"], f["text"])
    return out


# Gemini sometimes rewrites pseudonyms slightly: "[PATIENT_01]", "PATIENT_01", "[Patient 1]".
# Bracketed forms may use a space and inner padding; bare forms need the underscore, so ordinary
# text like "Type 2" is never touched. The surrounding spaces are never consumed.
_TAG_LIKE = re.compile(r"\[\s*([A-Za-z]+)[ _](\d+)\s*\]|\b([A-Za-z]+)_(\d+)\b")


def restore(answer: str, mapping: dict) -> str:
    """
    Swap pseudonyms in Gemini's answer back to real values. Unknown or invented ones are left alone.
    Shifted dates ("Aug 13") have no brackets: they are swapped back as exact whole words, in the
    same single pass, so a restored value is never replaced a second time.
    """
    plain = sorted((k for k in mapping if not k.startswith("[")), key=len, reverse=True)
    pattern = _TAG_LIKE.pattern
    if plain:
        pattern = r"(?<!\w)(?P<plain>" + "|".join(map(re.escape, plain)) + r")(?!\w)|" + pattern
    g = 1 if plain else 0                                     # the tag groups move up by one

    def swap(m: re.Match) -> str:
        if plain and m.group("plain"):
            return mapping[m.group("plain")]
        name, number = (m.group(g + 1), m.group(g + 2)) if m.group(g + 1) else (m.group(g + 3), m.group(g + 4))
        name = name.upper()
        for tag in (f"[{name}_{number}]", f"[{name}_{int(number):02d}]"):   # "PATIENT_1" -> [PATIENT_01]
            if tag in mapping:
                return mapping[tag]
        return m.group(0)
    return re.sub(pattern, swap, answer)


def tag_question(question: str, mapping: dict) -> str:
    """Replace any real values the clinician typed (e.g. the patient's name) with their pseudonyms."""
    # Longest values first, so "Jane Doe" is replaced before "Jane".
    # Whole words only: a masked age "74" must not turn "740 mg" into "[AGE_1]0 mg".
    for tag, value in sorted(mapping.items(), key=lambda kv: -len(kv[1])):
        question = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", lambda _m, t=tag: t,
                          question, flags=re.IGNORECASE)
    return question
