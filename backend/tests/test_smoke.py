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
    flags = pipeline.analyze(text)
    found = {f["text"]: f for f in flags}
    assert found["9123 947 241"]["label"] == "PHN" and found["9123 947 241"]["tier"] == "high"
    assert found["9123 947 241"]["locked"] and found["9123 947 241"]["masked"]
    assert "Parkinson's" not in found and "Foley" not in found      # never-redact list works
    assert "day 5" not in found and "7 days" not in found           # durations kept
    assert found["retired bush pilot"]["label"] == "Unique role" and found["retired bush pilot"]["tier"] == "med"
    reason = found["retired bush pilot"]["reason"]
    assert reason.startswith("5 details combined: ") and all(k in reason for k in ["age", "facility", "family", "role", "town"])
    assert [f["flag_code"] for f in flags] == [f"F{i}" for i in range(1, len(flags) + 1)]
    p = tagging.Pseudonyms()
    for f in flags:
        f["pseudonym"] = p.get(config.TYPES[f["type"]][2], f["text"])
    out = tagging.pseudonymize(text, flags)
    for secret in ["Margaret", "Ellison", "9123", "Tofino", "Raj", "claire.ellison", "555-0142", "Campbell"]:
        assert secret.lower() not in out.lower(), f"leaked: {secret}"
    assert "Parkinson's" in out and "7 days" in out                 # clinical meaning kept
    assert rules.looks_unsafe(out) is None
    return flags


def test_restore(flags):
    mapping = tagging.mapping_of(flags)
    patient = next(t for t, v in mapping.items() if v == "Margaret Ellison")
    assert patient == "[PATIENT_01]"
    answer = "[PATIENT_01] should rest. PATIENT_01 and [Patient 1] are fine. [PATIENT_99] unknown."
    restored = tagging.restore(answer, mapping)
    assert restored.count("Margaret Ellison") == 3 and "[PATIENT_99]" in restored
    assert tagging.tag_question("How is margaret ellison?", flags) == "How is [PATIENT_01]?"


def test_flask():
    import app as app_module
    import gemini_client
    gemini_client.ask = lambda note, history, q: "Fake answer about [PATIENT_01]"   # no real API call
    config.GEMINI_API_KEY = "test-key"
    c = app_module.app.test_client()

    # upload a ~600 KB file (Werkzeug would normally spill >500 KB to disk): must stay in memory (no temp file on disk)
    big = open("sample_note.txt", "rb").read() + b"\n" + b"x" * 600_000
    stream = app_module.InMemoryRequest._get_file_stream(None, None, None, None)
    assert isinstance(stream, io.BytesIO)
    config.MAX_TEXT_CHARS = 700_000                      # temporarily allow the big test file
    r = c.post("/documents", data={"file": (io.BytesIO(big), "note.txt")}, content_type="multipart/form-data")
    config.MAX_TEXT_CHARS = 200_000
    assert r.status_code == 201 and r.json["status"] == "needs_review"

    doc_id = r.json["id"]
    f = c.post(f"/documents/{doc_id}/finalize")
    assert f.status_code == 200 and f.json["status"] == "ready"

    ok = c.post("/chat", json={"document_ids": [doc_id], "message": "Summarize"})
    assert ok.status_code == 200 and ok.json["answer_with_pseudonyms"].startswith("Fake")
    assert ok.json["identifier_count"] == 0

    too_long = c.post("/documents", json={"title": "", "text": "a " * 150_000})
    assert too_long.status_code == 413


if __name__ == "__main__":
    setup()
    test_phn()
    flags = test_pipeline()
    test_restore(flags)
    test_flask()
    print("all smoke tests passed")
