"""Eval: default Presidio vs our pipeline on the held-out synthetic notes (CLAUDE.md section 13).

    python eval/run.py                 # held-out test set (the pitch number)
    python eval/run.py --set tuning    # the 5 tuning notes
    python eval/run.py --details       # also per-label recall and every miss

Systems
  presidio   Presidio's default AnalyzerEngine: all built-in recognizers, no custom rules.
             Everything it finds would be removed.
  rules      Our pipeline without GLiNER: Presidio + BC rules + BC lexicon (ablation).
  ours       Our full pipeline (backend/pipeline.analyze). A flag counts as removed only if it
             is masked by default, so LOW clinical flags that we show but keep don't count.

Scoring
  A labeled span is caught if any removed span overlaps it.
  Recall HIGH / MED = labeled identifiers caught / labeled identifiers.
  Clinical terms removed = labeled LOW spans (drug, dose, diagnosis, lab value) overlapped by a
  removed span. Target zero.
Both Presidio systems use the same spaCy model (config.SPACY_MODEL) so only the pipeline differs.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

EVAL = Path(__file__).resolve().parent
ROOT = EVAL.parent
sys.path.insert(0, str(ROOT / "backend"))

import config  # noqa: E402  (backend/config.py, loads .env)
from pipeline import analyze, lexicon, merge, risk, rules  # noqa: E402
from presidio_analyzer import AnalyzerEngine  # noqa: E402


def load(split: str) -> list[tuple[str, str, list[dict]]]:
    names = json.loads((EVAL / "split.json").read_text(encoding="utf-8"))
    ids = names["tuning"] + names["test"] if split == "all" else names[split]
    notes = []
    for note_id in ids:
        text = (EVAL / "notes" / f"{note_id}.txt").read_text(encoding="utf-8")
        labels = json.loads((EVAL / "labels" / f"{note_id}.json").read_text(encoding="utf-8"))
        notes.append((note_id, text, labels))
    return notes


# Each system returns the spans it would remove: [(start, end), ...]

_presidio_default = None


def presidio(text: str) -> list[tuple[int, int]]:
    global _presidio_default
    if _presidio_default is None:
        # Same spaCy engine as our rules, but a fresh default registry (no BC recognizers).
        _presidio_default = AnalyzerEngine(nlp_engine=rules._nlp, supported_languages=["en"])
    return [(r.start, r.end) for r in _presidio_default.analyze(text=text, language="en")]


def rules_only(text: str) -> list[tuple[int, int]]:
    spans = merge.merge(text, rules.find(text), [], lexicon.find(text))
    return [(f["start_idx"], f["end_idx"]) for f in risk.to_flags(text, spans) if f["masked"]]


def ours(text: str) -> list[tuple[int, int]]:
    return [(f["start_idx"], f["end_idx"]) for f in analyze(text) if f["masked"]]


SYSTEMS = {"presidio": presidio, "rules": rules_only, "ours": ours}
TITLES = {"presidio": "Presidio (default)", "rules": "Ours, no GLiNER", "ours": "Ours (full)"}


def caught(label: dict, removed: list[tuple[int, int]]) -> bool:
    return any(s < label["end"] and label["start"] < e for s, e in removed)


def score(notes, system) -> dict:
    by_tier = defaultdict(lambda: [0, 0])     # tier -> [caught, total]
    by_label = defaultdict(lambda: [0, 0])
    misses, removed_clinical = [], []
    seconds = 0.0
    for note_id, text, labels in notes:
        t0 = time.perf_counter()
        removed = system(text)
        seconds += time.perf_counter() - t0
        for lab in labels:
            hit = caught(lab, removed)
            by_tier[lab["tier"]][0] += hit
            by_tier[lab["tier"]][1] += 1
            by_label[lab["label"]][0] += hit
            by_label[lab["label"]][1] += 1
            if lab["tier"] != "low" and not hit:
                misses.append((note_id, lab))
            if lab["tier"] == "low" and hit:
                removed_clinical.append((note_id, lab))
    return {"tier": dict(by_tier), "label": dict(by_label), "misses": misses,
            "removed_clinical": removed_clinical, "seconds_per_note": seconds / max(1, len(notes))}


def pct(c: int, n: int) -> str:
    return f"{100 * c / n:5.1f}% ({c}/{n})" if n else "   n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", choices=["test", "tuning", "all"], default="test")
    ap.add_argument("--details", action="store_true", help="per-label recall and every miss")
    ap.add_argument("--systems", default="presidio,rules,ours")
    args = ap.parse_args()

    notes = load(args.set)
    systems = [s.strip() for s in args.systems.split(",")]
    gliner = "on" if config.USE_GLINER else "OFF (USE_GLINER=0), so 'ours' has no model"
    print(f"Set: {args.set}, {len(notes)} synthetic notes. spaCy: {config.SPACY_MODEL}. "
          f"GLiNER: {gliner}. Lexicon: {lexicon.load()}.\n")

    results = {name: score(notes, SYSTEMS[name]) for name in systems}

    def row(title, cells):
        print(f"{title:<34}" + "".join(f"{c:>22}" for c in cells))

    row("", [TITLES[s] for s in systems])
    row("Recall, direct identifiers (HIGH)", [pct(*r["tier"].get("high", [0, 0])) for r in results.values()])
    row("Recall, indirect identifiers (MED)", [pct(*r["tier"].get("med", [0, 0])) for r in results.values()])
    both = {s: [sum(r["tier"].get(t, [0, 0])[i] for t in ("high", "med")) for i in (0, 1)] for s, r in results.items()}
    row("Recall, all identifiers", [pct(*both[s]) for s in systems])
    row("Identifiers leaked", [str(both[s][1] - both[s][0]) for s in systems])
    row("Clinical terms wrongly removed", [pct(*r["tier"].get("low", [0, 0])) for r in results.values()])
    row("Seconds per note", [f"{r['seconds_per_note']:.2f}" for r in results.values()])

    if args.details:
        labels = sorted({lab for r in results.values() for lab in r["label"]})
        print("\nPer label (caught / total; for LOW labels this is wrongly removed):")
        for lab in labels:
            row(f"  {lab}", [pct(*r["label"].get(lab, [0, 0])) for r in results.values()])
        for name, r in results.items():
            print(f"\n{TITLES[name]}: missed identifiers")
            for note_id, lab in r["misses"]:
                print(f"  {note_id:<28} {lab['label']:<22} {lab['text']!r}")
            print(f"{TITLES[name]}: clinical terms removed")
            for note_id, lab in r["removed_clinical"]:
                print(f"  {note_id:<28} {lab['label']:<22} {lab['text']!r}")

    out = EVAL / "results" / f"{args.set}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "set": args.set, "notes": len(notes), "spacy_model": config.SPACY_MODEL,
        "gliner": config.USE_GLINER, "gliner_model": config.GLINER_MODEL,
        "gliner_threshold": config.GLINER_THRESHOLD,
        "systems": {name: {"tier": r["tier"], "label": r["label"],
                           "seconds_per_note": round(r["seconds_per_note"], 3)} for name, r in results.items()},
    }, indent=1) + "\n", encoding="utf-8")
    print(f"\nSaved {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    sys.exit(main())
