"""
Risk levels. Plain rules, no AI, so every decision is explainable.

- Direct identifiers (name, PHN, phone...) are RED: replaced unless the clinician keeps them.
- Quasi-identifiers (occupation, town, age...) are YELLOW: harmless alone.
- But 3+ DIFFERENT quasi types together ("74" + "Tofino" + "retired pilot") can point to
  one person, so the whole note becomes RED and those flags are escalated.
"""
import config


def score(spans: list[dict]) -> tuple[list[dict], str]:
    for s in spans:
        s["level"] = "RED" if s["type"] in config.DIRECT_TYPES else "YELLOW"

    quasi_kinds = {s["type"] for s in spans if s["type"] in config.QUASI_TYPES}

    if len(quasi_kinds) >= config.RED_COMBINATION:
        overall = "RED"
        for s in spans:
            if s["type"] in config.QUASI_TYPES:
                s["level"] = "RED"          # part of a risky combination
                s["reason"] = "combination: " + ", ".join(sorted(quasi_kinds))
    elif len(quasi_kinds) == 2:
        overall = "YELLOW"
    elif any(s["level"] == "RED" for s in spans):
        overall = "YELLOW"                  # only direct IDs: they'll be replaced, so moderate
    else:
        overall = "GREEN"

    # What the review screen pre-selects. RED = remove by default; YELLOW = clinician decides.
    for s in spans:
        s["remove_by_default"] = s["level"] == "RED"
    return spans, overall
