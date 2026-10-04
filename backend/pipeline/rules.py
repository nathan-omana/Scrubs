"""
Layer 1: Presidio + BC-specific rules.

Presidio's job here is ONLY to *find* things (the "analyzer"). We never use its
"anonymizer" to replace text, because replacing happens once, at the very end,
after GLiNER has also looked and the clinician has reviewed.
"""
import logging
import re

import tldextract
# PRIVACY FIX: Presidio's email checker uses `tldextract`, which by default DOWNLOADS a
# list of web domains from publicsuffix.org the first time it runs. No patient data is
# sent, but we promised no network calls during detection. This makes it use the copy
# that ships with the library instead.
tldextract.tldextract.TLD_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())

from presidio_analyzer import AnalyzerEngine, EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult  # noqa: E402
from presidio_analyzer.nlp_engine import NlpEngineProvider

import config
from .dates import find_dates


# ---------- BC Personal Health Number ----------
def is_valid_phn(value: str) -> bool:
    """
    BC PHN check: 10 digits, first digit 9, last digit is a mod-11 check digit.
    Weights for digits 2-9 come from the BC MSP spec ("PHN check digit routine").
    Known valid example from that spec: 9123947241.
    """
    d = re.sub(r"\D", "", value)                      # keep digits only ("9123 947 241" -> "9123947241")
    if len(d) != 10 or d[0] != "9":
        return False
    weights = [2, 4, 8, 5, 10, 9, 7, 3]                 # applied to digits 2..9
    total = sum(int(d[i + 1]) * w for i, w in enumerate(weights))
    check = 11 - (total % 11)                           # 10 or 11 means "not a valid PHN"
    return check < 10 and check == int(d[9])


class BCPHNRecognizer(PatternRecognizer):
    """Regex finds 10-digit numbers starting with 9; validate_result() keeps only real PHNs."""

    def __init__(self):
        super().__init__(
            supported_entity="PHN",
            patterns=[Pattern("bc_phn", r"\b9\d{3}[ .-]?\d{3}[ .-]?\d{3}\b", 0.5)],
        )

    def validate_result(self, pattern_text: str) -> bool:
        # Presidio calls this for every regex match. True -> confidence boosted to max. False -> dropped.
        return is_valid_phn(pattern_text)


# ---------- MRN (Medical Record Number) ----------
class MRNRecognizer(EntityRecognizer):
    """Flags the digit portion of MRN annotations, e.g. '9482-110' in 'MRN: 9482-110'."""
    _RE = re.compile(r"\bMRN[\s:#-]*(\d[\d -]{2,9}\d)\b", re.IGNORECASE)

    def __init__(self):
        super().__init__(supported_entities=["MRN"], name="MRNRecognizer")

    def load(self): pass

    def analyze(self, text, entities, nlp_artifacts=None):
        return [
            RecognizerResult("MRN", m.start(1), m.end(1), 0.9)
            for m in self._RE.finditer(text)
        ]


# ---------- Street address (a safety net: GLiNER also finds addresses) ----------
class StreetAddressRecognizer(EntityRecognizer):
    """
    "4820 Marine Ave", "12 Old Bridge Road", "1050-B..." style street addresses. Case-SENSITIVE on
    purpose: the street name and type must be capitalized, so "2 weeks" or "5 mg" never match.
    A custom recognizer because Presidio's PatternRecognizer adds IGNORECASE by default.
    """
    _RE = re.compile(
        r"\b\d{1,6}(?:-\d{1,6})?\s+(?:[A-Z][a-z]+\.?\s+){1,3}"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Way|Crescent|Cres|Lane|Ln|Place|Pl"
        r"|Court|Ct|Highway|Hwy|Terrace|Trail|Close|Row)\b\.?"
    )

    def __init__(self):
        super().__init__(supported_entities=["ADDRESS"], name="StreetAddressRecognizer")

    def load(self): pass

    def analyze(self, text, entities, nlp_artifacts=None):
        return [RecognizerResult("ADDRESS", m.start(), m.end(), 0.7) for m in self._RE.finditer(text)]


# ---------- Prescriber license (CPSBC and similar) ----------
class LicenseRecognizer(EntityRecognizer):
    """The number after a license word: "CPSBC #34567", "License: 12345", "College ID 40912"."""
    _RE = re.compile(
        r"\b(?:licen[cs]e|CPSBC|College\s+(?:ID|No\.?)|prescriber|practitioner)\s*(?:no\.?|number|#|ID)?"
        r"[\s:#-]*([A-Z]{0,2}\d{4,6})\b",
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__(supported_entities=["LICENSE"], name="LicenseRecognizer")

    def load(self): pass

    def analyze(self, text, entities, nlp_artifacts=None):
        return [RecognizerResult("LICENSE", m.start(1), m.end(1), 0.9) for m in self._RE.finditer(text)]


# ---------- Context-aware date recognizer ----------
class ContextDateRecognizer(EntityRecognizer):
    """
    Flags dates that follow explicit date-context labels (DOB, Date of Service, Date of Birth).
    Presidio's built-in DATE_TIME can miss these when confidence is borderline.
    """
    _RE = re.compile(
        r"\b(?:DOB|Date\s+of\s+(?:Service|Birth))[\s:]+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__(supported_entities=["DATE_TIME"], name="ContextDateRecognizer")

    def load(self): pass

    def analyze(self, text, entities, nlp_artifacts=None):
        return [
            RecognizerResult("DATE_TIME", m.start(1), m.end(1), 0.95)
            for m in self._RE.finditer(text)
        ]


class RunningTextDateRecognizer(EntityRecognizer):
    """
    Dates written in running text that spaCy's small model misses: "Sep 28", "28 Sept",
    "Sept. 28th", "September 21, 2026". Same finder tagging.py uses for chat (pipeline/dates.py).
    """

    def __init__(self):
        super().__init__(supported_entities=["DATE_TIME"], name="RunningTextDateRecognizer")

    def load(self): pass

    def analyze(self, text, entities, nlp_artifacts=None):
        return [RecognizerResult("DATE_TIME", s, e, 0.85) for s, e in find_dates(text)]


# Presidio logs at INFO level (noisy, and debug logs could include text). Errors only.
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

# ---------- Build the analyzer once (loading spaCy is slow) ----------
_nlp = NlpEngineProvider(nlp_configuration={
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": config.SPACY_MODEL}],
}).create_engine()

analyzer = AnalyzerEngine(nlp_engine=_nlp, supported_languages=["en"])
analyzer.registry.add_recognizer(BCPHNRecognizer())
analyzer.registry.add_recognizer(MRNRecognizer())
analyzer.registry.add_recognizer(ContextDateRecognizer())
analyzer.registry.add_recognizer(RunningTextDateRecognizer())
analyzer.registry.add_recognizer(StreetAddressRecognizer())
analyzer.registry.add_recognizer(LicenseRecognizer())

# Canadian postal code, e.g. "V0R 2Z0". (First letter can't be D, F, I, O, Q, U, W, Z.)
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="POSTAL",
    patterns=[Pattern("ca_postal", r"\b[ABCEGHJ-NPRSTVXY]\d[A-Z] ?\d[A-Z]\d\b", 0.8)],
))

# BC facility names: exact list match ("deny list" = words to flag).
analyzer.registry.add_recognizer(PatternRecognizer(
    supported_entity="FACILITY",
    deny_list=config.BC_FACILITIES,
))


# Durations like "7 days" or "3 years" are clinically useful and NOT dates.
# Presidio's DATE_TIME catches them anyway, so we drop those.
_DURATION = re.compile(
    r"^(\d+|a|an|one|two|three|several)\s*(-\s*)?(day|week|month|year|hour|minute)s?(\s*-?\s*old)?$",
    re.IGNORECASE,
)


# Relative hospital days ("day 5", "POD 2") are also clinically useful, not identifying.
_RELATIVE_DAY = re.compile(r"^(post-?op\s+)?(day|pod)\s*\d+$", re.IGNORECASE)


# A month as a whole word ("Sept", "September", "Mar."), not inside "summary" or "primary".
_MONTH = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?(?![a-z])", re.IGNORECASE)
# Numeric dates: 2026-09-02, 03/14/1951, 3/14, 03-14-1951. Not "4.2", "2-3", "10:30" or a lone number.
_NUMERIC_DATE = re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}(/\d{2,4})?|\d{1,2}-\d{1,2}-\d{2,4})\b")


def _is_real_date(text: str) -> bool:
    t = text.strip()
    if _DURATION.match(t) or _RELATIVE_DAY.match(t):
        return False
    if "year-old" in t.lower() or "yo" == t.lower():
        return False                                    # that's an age; GLiNER labels ages
    # A date needs a month name or a numeric date shape. A lone number ("2", "28", "2026") is
    # not a date: Presidio flags question numbers and counts that way, and masking them breaks text.
    return bool(_MONTH.search(t) or _NUMERIC_DATE.search(t))


# A bare "7/10" with no year is far more often a score than a date: pain 7/10, power 4/5, VAS 3/10.
# Shifting it as a date would silently change a clinical value, so look at the words around it.
_BARE_SLASH = re.compile(r"(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])")
_SCORE_BEFORE = re.compile(r"(?:pain|score[ds]?|rated|rates|rating|severity|intensity|VAS|NRS|GCS|strength|power"
                           r"|grade|out of)\W*(?:\w+\W+){0,2}$", re.IGNORECASE)
_SCORE_AFTER = re.compile(r"\s*(?:pain|on\b|scale|strength)", re.IGNORECASE)
_DATE_CUE_BEFORE = re.compile(r"\b(?:on|since|from|until|dated?|seen|admitted|discharged)\s*$", re.IGNORECASE)


def _is_score(text: str, start: int, end: int) -> bool:
    """
    True if Presidio's DATE_TIME at text[start:end] is really a bare d/d score. Its span can be
    wider than the number ("3/10 overnight"), so look at the d/d inside it. A month name or a
    year anywhere in the span means it's a date.
    """
    found = text[start:end]
    m = _BARE_SLASH.search(found)
    if not m or _MONTH.search(found) or re.search(r"\d{4}|\d+/\d+/\d+|\d+-\d+-\d+", found):
        return False
    start, end = start + m.start(), start + m.end()
    if _SCORE_BEFORE.search(text[max(0, start - 30):start]) or _SCORE_AFTER.match(text, end):
        return True
    first, second = (int(n) for n in m.group().split("/"))
    return second == 10 and first <= 10 and not _DATE_CUE_BEFORE.search(text[max(0, start - 15):start])


def find(text: str) -> list[dict]:
    """Return every rule-based finding as {start, end, type, score, source}."""
    results = analyzer.analyze(text=text, language="en", entities=config.PRESIDIO_ENTITIES)
    spans = []
    for r in results:
        found = text[r.start:r.end]
        if r.entity_type == "DATE_TIME" and (not _is_real_date(found) or _is_score(text, r.start, r.end)):
            continue
        spans.append({
            "start": r.start,
            "end": r.end,
            "type": config.PRESIDIO_RENAME.get(r.entity_type, r.entity_type),
            "score": round(r.score, 2),
            "source": "rules",
        })
    return spans


# ---------- Last-resort check used right before anything is sent to Gemini ----------
_PHN_ANYWHERE = re.compile(r"\b9\d{3}[ .-]?\d{3}[ .-]?\d{3}\b")      # 9123947241, 9123 947 241, 9123-947-241, 9123.947.241
_EMAIL_ANYWHERE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def looks_unsafe(text: str) -> str | None:
    """Return a reason string if outgoing text still contains a raw PHN or email, else None."""
    for m in _PHN_ANYWHERE.finditer(text):
        if is_valid_phn(m.group()):
            return "raw PHN found"
    if _EMAIL_ANYWHERE.search(text):
        return "raw email found"
    return None
