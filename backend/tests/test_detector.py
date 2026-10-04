"""
Layer 2 plumbing (GLiNER is faked): chunking, offsets, labels.
Run from the backend folder:   python -m tests.test_detector
"""
import config
from pipeline import detector
from tests._util import run, use_fake_gliner


def test_chunks_cover_the_whole_text_exactly_once():
    text = "".join(f"Line {i} has some words in it.\n" for i in range(300))
    chunks = detector._chunks(text, 1200)
    assert "".join(c for _, c in chunks) == text
    for offset, chunk in chunks:
        assert text[offset:offset + len(chunk)] == chunk


def test_chunks_never_exceed_the_limit():
    # pdf.py rejoins wrapped lines, so a whole paragraph often arrives as ONE long line.
    # GLiNER only reads ~384 tokens; anything past that in a chunk is silently ignored.
    paragraph = " ".join(["The patient reports mild fatigue and stable appetite."] * 60)   # ~3,300 chars
    text = "Header\n" + paragraph + "\nFooter\n"
    for _, chunk in detector._chunks(text, 1200):
        assert len(chunk) <= 1200, f"chunk of {len(chunk)} chars"


def test_offsets_map_back_to_the_full_note():
    fake = use_fake_gliner({"Margaret Ellison": "person name", "Tofino": "city or town"})
    filler = "".join(f"Filler line {i} about vitals.\n" for i in range(100))
    text = filler + "Patient Margaret Ellison from Tofino.\n" + filler + "Tofino again.\n"
    spans = detector.detect(text)
    assert len(fake.calls) > 1, "test text should need several chunks"
    assert sorted(text[s["start"]:s["end"]] for s in spans) == ["Margaret Ellison", "Tofino", "Tofino"]
    for s in spans:
        assert s["source"] == "gliner" and 0 <= s["score"] <= 1


def test_labels_map_to_types():
    use_fake_gliner({label: label for label in ["person name", "doctor", "family member"]})
    text = "person name, doctor, family member"
    types = {text[s["start"]:s["end"]]: s["type"] for s in detector.detect(text)}
    assert types == {"person name": "PERSON", "doctor": "PROVIDER", "family member": "RELATION"}


def test_every_label_type_has_a_tier():
    assert set(config.GLINER_LABELS.values()) <= set(config.TYPES)


def test_every_label_has_a_type():
    assert config.GLINER_LABELS and all(config.GLINER_LABELS.values())


def test_use_gliner_off_returns_nothing():
    use_fake_gliner({"Tofino": "city or town"})
    config.USE_GLINER = False
    try:
        assert detector.detect("Tofino") == []
    finally:
        config.USE_GLINER = True


def test_empty_text():
    use_fake_gliner({})
    assert detector.detect("") == []


if __name__ == "__main__":
    run(globals())
