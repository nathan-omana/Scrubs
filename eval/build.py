"""Builds eval/notes/*.txt and eval/labels/*.json from the hand-annotated notes in eval/annotated/.

Annotations are inline: [[the retired town pharmacist|Unique role]]. The markup is stripped to
make the plain note, and each span's position in the plain note becomes a label:
    {"start": 120, "end": 147, "label": "Unique role", "tier": "med", "text": "the retired town pharmacist"}

Edit the files in eval/annotated/, then run:  python eval/build.py
Never edit eval/notes/ or eval/labels/ by hand; they are overwritten.
"""

import json
import re
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parent

# Label -> tier, from CLAUDE.md sections 6 and 8. "Clinical term" covers eponym devices and
# procedures (Foley catheter) that aren't a drug, dose, diagnosis or lab value.
TIERS = {
    "Person": "high",
    "PHN": "high",
    "MRN": "high",
    "License": "high",
    "Address": "high",
    "Phone": "high",
    "Email": "high",
    "Date": "med",
    "Age": "med",
    "Location description": "med",
    "Unique role": "med",
    "Family detail": "med",
    "Employer": "med",
    "Person description": "med",
    "Drug": "low",
    "Dose": "low",
    "Diagnosis": "low",
    "Lab value": "low",
    "Clinical term": "low",
}

SPAN = re.compile(r"\[\[([^\[\]|]+)\|([^\[\]|]+)\]\]")


def parse(annotated: str) -> tuple[str, list[dict]]:
    text, labels, pos = [], [], 0
    for m in SPAN.finditer(annotated):
        text.append(annotated[pos:m.start()])
        start = sum(len(t) for t in text)
        span_text, label = m.group(1), m.group(2).strip()
        if label not in TIERS:
            raise ValueError(f"unknown label {label!r} on {span_text!r}")
        if span_text != span_text.strip():
            raise ValueError(f"span has leading or trailing spaces: {span_text!r}")
        text.append(span_text)
        labels.append({"start": start, "end": start + len(span_text), "label": label,
                       "tier": TIERS[label], "text": span_text})
        pos = m.end()
    text.append(annotated[pos:])
    plain = "".join(text)
    if "[[" in plain or "]]" in plain:
        raise ValueError("unbalanced [[ ]] markup")
    for lab in labels:  # offsets must point at the right text
        assert plain[lab["start"]:lab["end"]] == lab["text"]
    return plain, labels


def main() -> int:
    notes_dir, labels_dir = EVAL / "notes", EVAL / "labels"
    notes_dir.mkdir(exist_ok=True)
    labels_dir.mkdir(exist_ok=True)
    errors = 0
    files = sorted((EVAL / "annotated").glob("*.txt"))
    for path in files:
        try:
            plain, labels = parse(path.read_text(encoding="utf-8"))
        except (ValueError, AssertionError) as exc:
            print(f"{path.name}: {exc}")
            errors += 1
            continue
        (notes_dir / path.name).write_text(plain, encoding="utf-8", newline="\n")
        (labels_dir / f"{path.stem}.json").write_text(json.dumps(labels, indent=1) + "\n", encoding="utf-8", newline="\n")
    counts = {}
    for path in labels_dir.glob("*.json"):
        for lab in json.loads(path.read_text(encoding="utf-8")):
            counts[lab["tier"]] = counts.get(lab["tier"], 0) + 1
    print(f"Built {len(files) - errors} notes. Labeled spans: "
          + ", ".join(f"{counts.get(t, 0)} {t.upper()}" for t in ("high", "med", "low")))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
