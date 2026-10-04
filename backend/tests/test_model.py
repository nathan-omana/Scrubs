"""
The REAL GLiNER model on synthetic notes. Slower (~10 s to load), and needs the model in the
Hugging Face cache (run demo.py once). Runs fully offline: HF_HUB_OFFLINE=1 and sockets blocked.
Skipped, not failed, when the model isn't downloaded.

Run from the backend folder:   python -m tests.test_model
"""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # must be set before huggingface_hub is imported

import sys                                                        # noqa: E402
from pathlib import Path                                          # noqa: E402

import config                                                     # noqa: E402
import pipeline                                                   # noqa: E402
from pipeline import detector, lexicon, tagging                   # noqa: E402
from tests._util import run                                       # noqa: E402
from tests.test_privacy import NoNetwork                          # noqa: E402

NOTE = (Path(__file__).resolve().parents[1] / "sample_note.txt").read_text()
CACHE = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def _model_cached() -> bool:
    return (CACHE / ("models--" + config.GLINER_MODEL.replace("/", "--"))).exists()


def analyze(text):
    with NoNetwork() as net:
        r = pipeline.analyze(text)
    assert net.attempts == [], f"network attempted: {net.attempts}"
    return r


def tag_everything(text):
    """Mask every flag (as if the clinician masked all), return (flags, pseudonymized text)."""
    flags = analyze(text)
    p = tagging.Pseudonyms()
    for f in flags:
        f["masked"] = True
        f["pseudonym"] = p.get(config.TYPES[f["type"]][2], f["text"])
    return flags, tagging.pseudonymize(text, flags)


def test_sample_note_no_leaks():
    r, tagged = tag_everything(NOTE)
    for s in ["Margaret", "Ellison", "9123", "03/14/1951", "Campbell", "V0R 2Z0", "555-0142",
              "Tofino", "bush pilot", "74-year-old", "Claire", "claire.ellison", "Raj", "Patel"]:
        assert s.lower() not in tagged.lower(), f"leaked: {s}"
    assert {f["tier"] for f in r} >= {"high", "med"}


def test_sample_note_keeps_clinical_terms():
    _, tagged = tag_everything(NOTE)
    for s in ["Parkinson's disease", "UTI", "Foley catheter", "removed day 5", "nitrofurantoin 100 mg BID",
              "x 7 days", "in 2 weeks", "Pt is a"]:
        assert s in tagged, f"over-redacted: {s}"


def test_names_found_by_gliner_itself():
    found = {f["text"]: f for f in analyze(NOTE)}
    for name in ["Margaret Ellison", "Dr. Raj Patel"]:
        assert name in found and "gliner" in found[name]["found_by"], (name, found.get(name))


def test_name_at_the_end_of_a_long_paragraph():
    # PDF extraction joins a paragraph into one long line. A name near its end must still be found.
    # GLiNER itself must find it: spaCy backs up names, but nothing backs up occupations or
    # family details, so a GLiNER blind spot there is a leak.
    filler = " ".join(["Vitals stable overnight, tolerating diet, mobilizing with walker."] * 40)
    text = filler + " Discussed plan with patient Margaret Ellison and her son.\n"
    found = {f["text"]: f for f in analyze(text)}
    assert "Margaret Ellison" in found and "gliner" in found["Margaret Ellison"]["found_by"], \
        "GLiNER missed a name at the end of a long line"


if __name__ == "__main__":
    if not _model_cached():
        print(f"test_model: SKIPPED ({config.GLINER_MODEL} not in {CACHE}; run demo.py once)")
        sys.exit(0)
    config.USE_GLINER = True
    detector._model = None
    lexicon.LEXICON_SOURCE, lexicon._entries = "csv", None
    run(globals())
