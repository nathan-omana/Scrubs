"""
Pseudonyms, pseudonymizing and restoring (CLAUDE.md section 8). No AI here, just find-and-replace.

The browser re-identifies Gemini's answer with the mapping from GET /documents/{id}/mapping.
restore() is the same logic in Python, for demo.py and the tests, and as a reference for the frontend.
"""
import re

import config
from .dates import find_dates, parse, same_day

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


# ---------- Variants of a masked value ----------
# pseudonymize(), tag_question() and the leak check in app.py all find a masked value's other
# appearances through variant_spans(), so what we hide and what we check can never disagree.
#
# Trade-off, on purpose: a surname that is also an everyday word ("Park", "Hope") is replaced
# wherever it appears. Over-masking costs a little readability; a miss is a leak.

NAME_TYPES = {"PERSON", "PROVIDER"}
NUMBER_TYPES = {"PHONE", "PHN", "MRN", "LICENSE"}
# Words in a name that say nothing on their own: particles, titles, and relation words that
# spaCy sometimes includes in a name ("Daughter Claire").
_NAME_STOPWORDS = {"van", "von", "der", "den", "del", "des", "la", "le", "los", "the", "and",
                   "mr", "mrs", "ms", "miss", "mx", "dr", "doctor", "prof",
                   "daughter", "son", "wife", "husband", "mother", "father", "sister", "brother"}
_NAME_WORD = re.compile(r"\w+(?:['’]\w+)*")
_POSSESSIVE = re.compile(r"['’]s$", re.IGNORECASE)


def _whole_word(value: str) -> str:
    # (?<!\w) / (?!\w) instead of \b: \b needs a letter or digit at the edge, so a value
    # that starts with "(" like "(250) 555-0142" would never match and its repeats would leak.
    return r"(?<!\w)" + re.escape(value) + r"(?!\w)"


def _name_words(value: str) -> list[str]:
    """ "Mrs. Eleanor Park" -> ["Eleanor", "Park"]; "Okafor's" -> ["Okafor"]."""
    words = (_POSSESSIVE.sub("", w) for w in _NAME_WORD.findall(_TITLES.sub("", value.strip())))
    return [w for w in words if len(w) >= 3 and w.lower() not in _NAME_STOPWORDS
            and w.lower() not in config.NEVER_REDACT]


def _part_patterns(flag: dict) -> list[str]:
    """Regexes for a flag's partial forms: each word of a name, or a number in any layout."""
    kind, value = flag.get("type"), flag["text"]
    if kind in NAME_TYPES:
        return [_whole_word(w) for w in _name_words(value)]
    if kind in NUMBER_TYPES:
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 6:     # (604) 555-0187 = 604-555-0187 = 6045550187; 9487 312 652 = 9487312652
            return [r"(?<!\d)" + r"[\s().+-]*".join(digits) + r"(?!\d)"]
    return []


def _same_dates(text: str, flag: dict) -> list[tuple[int, int]]:
    """For a date flag, the same day written any other way: "september 28", "28 Sept" for "Sept 28"."""
    day = parse(flag["text"])
    return [(s, e) for s, e in find_dates(text) if same_day(parse(text[s:e]), day)] if day else []


def variant_spans(text: str, flag: dict, whole: bool = True, parts: bool = True,
                  min_len: int = config.MIN_REPEAT_CHARS) -> list[tuple[int, int]]:
    """
    Every (start, end) in `text` where this flag's value appears again:
      whole: the full value, whole word, any case, if it has at least `min_len` characters.
             Shorter values ("Al", "2") are only replaced where they were flagged.
      parts: each word of a name ("Okafor" from "Daniel Okafor"), the digits of a phone,
             PHN, MRN or license number written any other way, or the same day written as
             another date ("28 Sept" for "Sept 28").
    """
    patterns = []
    value = flag["text"].strip()
    if whole and value and len(value) >= min_len:
        patterns.append(_whole_word(value))
    if parts:
        patterns += _part_patterns(flag)
    spans = [(m.start(), m.end()) for p in patterns for m in re.finditer(p, text, re.IGNORECASE)]
    if parts and flag.get("type") == "DATE":
        spans += _same_dates(text, flag)
    return spans


def pseudonymize(text: str, flags: list[dict]) -> str:
    """
    Replace every masked flag with its pseudonym. Unmasked flags stay as original text.

    SAFETY: if "Tofino" is masked once, every OTHER occurrence of "Tofino" (any case, whole word)
    is replaced too, even where no detector flagged it, and so are partial forms ("Mr. Okafor"
    for "Daniel Okafor", "6045550187" for "(604) 555-0187"). Otherwise one miss = one leak.
    Flagged spots go first, then every full value, then partial forms, so "Claire Park" as a
    whole wins over the word "Park" from "Eleanor Park".
    """
    masked = [f for f in flags if f["masked"]]
    edits = [(f["start_idx"], f["end_idx"], f["pseudonym"]) for f in masked]
    taken = [(s, e) for s, e, _ in edits]
    for whole in (True, False):
        for f in masked:
            for s, e in variant_spans(text, f, whole=whole, parts=not whole):
                if not any(s < te and e > ts for ts, te in taken):
                    edits.append((s, e, f["pseudonym"]))
                    taken.append((s, e))

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


def tag_question(question: str, flags: list[dict]) -> str:
    """
    Replace any real values the clinician typed (the patient's name, "Mr. Okafor", a phone number
    in another layout) with their pseudonyms. Uses the same variants as pseudonymize(), plus
    short values: a question is short, so a masked age "94" is replaced too.
    """
    found = [(s, e, f["pseudonym"]) for f in flags if f["masked"]
             for s, e in variant_spans(question, f, min_len=1)]
    # Longest first, so "Jane Doe" is replaced as a whole before "Jane" alone.
    # Whole words only: a masked age "74" must not turn "740 mg" into "[AGE_1]0 mg".
    edits: list[tuple[int, int, str]] = []
    for s, e, tag in sorted(found, key=lambda x: (x[0] - x[1], x[0])):
        if not any(s < te and e > ts for ts, te, _ in edits):
            edits.append((s, e, tag))
    for s, e, tag in sorted(edits, reverse=True):
        question = question[:s] + tag + question[e:]
    return question
