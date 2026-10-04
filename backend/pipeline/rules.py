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


def _is_real_date(text: str) -> bool:
    t = text.strip()
    if _DURATION.match(t) or _RELATIVE_DAY.match(t):
        return False
    if not re.search(r"\d", t) and not re.search(
        r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", t, re.IGNORECASE
    ):
        return False                                    # "daily", "today", "yesterday" -> not a date
    if "year-old" in t.lower() or "yo" == t.lower():
        return False                                    # that's an age; GLiNER labels ages
    return True


def find(text: str) -> list[dict]:
    """Return every rule-based finding as {start, end, type, score, source}."""
    results = analyzer.analyze(text=text, language="en", entities=config.PRESIDIO_ENTITIES)
    spans = []
    for r in results:
        found = text[r.start:r.end]
        if r.entity_type == "DATE_TIME" and not _is_real_date(found):
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
