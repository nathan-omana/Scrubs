"""
Tiers, labels and reasons (CLAUDE.md section 6). Plain rules, no AI, so every decision is explainable.

- HIGH (names, PHN, MRN, address, phone, email): masked and locked.
- MED (dates, towns, roles, family details...): masked, the clinician can unmask.
- LOW (drugs, doses, diagnoses, lab values): kept, the clinician can mask.
- Quasi-identifiers are harmless alone, but 3+ different kinds in one note ("74" + "Tofino" +
  "retired pilot") can point to one person, so their reason says so.
"""
import re

import config

# Which pass found it, in the words the frontend uses (lib/types.ts Flag.source).
SOURCE = {"rules": "presidio", "gliner": "model", "lexicon": "lexicon"}

REASONS = {
    "PERSON": "Patient or other person's name",
    "PROVIDER": "Provider name",
    "PHN": "BC PHN, check digit valid",
    "MRN": "Medical record number",
    "LICENSE": "Prescriber license number",
    "ADDRESS": "Street address",
    "POSTAL": "Canadian postal code",
    "PHONE": "Phone number",
    "EMAIL": "Email address",
    "DATE": "Exact date",
    "AGE": "Age over 89",
    "LOCATION": "Names a town or place",
    "FACILITY": "Names a facility",
    "OCCUPATION": "Role that can single out a person",
    "RELATION": "Family member or detail",
    "ORG": "Names an employer",
    "DESC": "Describes the person",
    "DRUG": "Clinical term, kept by default",
    "DOSE": "Clinical term, kept by default",
    "DIAGNOSIS": "Clinical term, kept by default",
    "LAB": "Clinical term, kept by default",
}

# Plain words for the "N details combined" reason.
KIND_WORDS = {"OCCUPATION": "role", "LOCATION": "town", "FACILITY": "facility", "AGE": "age",
              "RELATION": "family", "ORG": "employer", "DESC": "description"}

_DOCTOR_BEFORE = re.compile(r"\b(dr|doctor)\.?\s*$", re.IGNORECASE)
_DOCTOR_START = re.compile(r"^(dr|doctor)\.?\s", re.IGNORECASE)


def _type(text: str, span: dict) -> str:
    """A PERSON written as "Dr. X" (or right after "Dr.") is a provider, not the patient."""
    t = span["type"]
    if t == "PERSON" and (_DOCTOR_START.match(span["text"])
                          or _DOCTOR_BEFORE.search(text[max(0, span["start"] - 8):span["start"]])):
        return "PROVIDER"
    return t if t in config.TYPES else "DESC"     # unknown types are treated as MED, never dropped


def to_flags(text: str, spans: list[dict]) -> list[dict]:
    """
    Merged spans (sorted, non-overlapping) -> flags in reading order: F1, F2...
    Each flag has the lib/types.ts fields except `pseudonym` (assigned per session by the API),
    plus two internal fields: `type` (for the pseudonym prefix) and `found_by` (for eval and tests).
    """
    types = [_type(text, s) for s in spans]
    quasi = sorted({KIND_WORDS[t] for t in types if t in config.QUASI_TYPES})
    combined = f"{len(quasi)} details combined: {', '.join(quasi)}" if len(quasi) >= config.COMBINATION_MIN else None

    flags = []
    for i, (s, t) in enumerate(zip(spans, types)):
        label, tier, _prefix = config.TYPES[t]
        reason = combined if (combined and t in config.QUASI_TYPES) else REASONS.get(t, label)
        flags.append({
            "flag_code": f"F{i + 1}",
            "start_idx": s["start"],
            "end_idx": s["end"],
            "text": s["text"],
            "label": label,
            "tier": tier,
            "reason": reason,
            "masked": tier != "low",
            "locked": tier == "high",
            "source": SOURCE[s["source"]],
            "type": t,
            "found_by": s["found_by"],
        })
    return flags
