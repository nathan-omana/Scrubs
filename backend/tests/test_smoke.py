"""
Quick checks that run WITHOUT downloading GLiNER or calling Gemini (both are faked).
Run from the backend folder:   python -m tests.test_smoke
"""
import io
import re

import config
from pipeline import detector, rules, tagging
import pipeline


class FakeGLiNER:
    """Pretends to be GLiNER: returns fixed phrases wherever they appear in the chunk."""
    PHRASES = {"Margaret Ellison": "person name", "retired bush pilot": "occupation",
               "Tofino": "city or town", "74-year-old": "age", "Daughter": "family member",
               "Claire": "person name", "211 Campbell St": "street address", "Raj Patel": "person name"}

    def predict_entities(self, text, labels, threshold=0.5):
        out = []
        for phrase, label in self.PHRASES.items():
            for m in re.finditer(re.escape(phrase), text):
                out.append({"start": m.start(), "end": m.end(), "text": phrase, "label": label, "score": 0.9})
        return out


def setup():
    config.USE_GLINER = True
    detector._model = FakeGLiNER()          # skip the real download


def test_phn():
    assert rules.is_valid_phn("9123947241")          # example from the BC spec
    assert rules.is_valid_phn("9123 947 241")
    assert not rules.is_valid_phn("9123947242")      # wrong check digit
    assert not rules.is_valid_phn("8123947241")      # must start with 9


def test_pipeline():
    text = open("sample_note.txt").read()
    result = pipeline.analyze(text)
    found = {s["text"]: s for s in result["spans"]}
    assert found["9123 947 241"]["type"] == "PHN"
    assert "Parkinson's" not in found and "Foley" not in found      # never-redact list works
    assert "day 5" not in found and "7 days" not in found           # durations kept
    assert "retired bush pilot" in found and found["retired bush pilot"]["type"] == "OCCUPATION"
    assert result["risk"] == "RED"                                  # town + age + occupation + relation
    tagged, mapping = tagging.tag_text(text, result["spans"], {s["id"] for s in result["spans"]})
    for secret in ["Margaret", "Ellison", "9123", "Tofino", "Raj", "claire.ellison", "555-0142", "Campbell"]:
        assert secret.lower() not in tagged.lower(), f"leaked: {secret}"
    assert "Parkinson's" in tagged and "7 days" in tagged           # clinical meaning kept
    assert rules.looks_unsafe(tagged) is None
    return mapping


def test_restore(mapping):
    person = next(t for t, v in mapping.items() if v == "Margaret Ellison")
    n = person.strip("[]").split("_")[1]
    answer = f"{person} should rest. PERSON_{n} and [Person {n}] are fine. [PERSON_99] unknown."
    restored = tagging.restore(answer, mapping)
    assert restored.count("Margaret Ellison") == 3 and "[PERSON_99]" in restored
    assert tagging.tag_question("How is margaret ellison?", mapping) == f"How is {person}?"


def test_flask():
    import app as app_module
    import gemini_client
    gemini_client.ask = lambda note, history, q: "Fake answer about [PERSON_1]"   # no real API call
    c = app_module.app.test_client()

    # upload a ~600 KB file (Werkzeug would normally spill >500 KB to disk): must stay in memory (no temp file on disk)
    big = open("sample_note.txt", "rb").read() + b"\n" + b"x" * 600_000
    stream = app_module.InMemoryRequest._get_file_stream(None, None, None, None)
    assert isinstance(stream, io.BytesIO)
    config.MAX_TEXT_CHARS = 700_000                      # temporarily allow the big test file
    r = c.post("/analyze", data={"file": (io.BytesIO(big), "note.txt")}, content_type="multipart/form-data")
    config.MAX_TEXT_CHARS = 200_000
    assert r.status_code == 200 and r.json["risk"] == "RED"

    spans = r.json["spans"]
    t = c.post("/tag", json={"text": r.json["text"], "spans": spans, "remove_ids": [s["id"] for s in spans]})
    assert t.status_code == 200

    ok = c.post("/chat", json={"tagged_note": t.json["tagged_text"], "history": [], "question": "Summarize"})
    assert ok.status_code == 200 and ok.json["answer"].startswith("Fake")

    too_long = c.post("/analyze", json={"text": "a " * 150_000})
    assert too_long.status_code == 413

    blocked = c.post("/chat", json={"tagged_note": "PHN 9123947241", "history": [], "question": "hi"})
    assert blocked.status_code == 400                          # raw PHN never leaves


if __name__ == "__main__":
    setup()
    test_phn()
    mapping = test_pipeline()
    test_restore(mapping)
    test_flask()
    print("all smoke tests passed")
