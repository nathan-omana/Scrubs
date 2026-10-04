"""
The section 10 API, checked against the frontend contract in lib/types.ts (Doc, Flag, ChatResponse).
GLiNER and Gemini are faked. Run from the backend folder:   python -m tests.test_api
"""
import io
from datetime import datetime

import app as app_module
import config
import gemini_client
from tests._util import run, use_fake_gliner
from tests.pdf_factory import build_pdf

NOTE = open("sample_note.txt").read()
GLINER_PHRASES = {"Margaret Ellison": "person name", "bush pilot": "occupation", "Tofino": "city or town",
                  "74-year-old": "age", "Claire": "family member", "211 Campbell St": "street address",
                  "Dr. Raj Patel": "doctor"}

# lib/types.ts, exactly.
DOC_KEYS = {"id", "title", "source", "original_text", "pseudonymized_text", "status", "created_at", "flags"}
FLAG_KEYS = {"flag_code", "start_idx", "end_idx", "text", "label", "tier", "reason", "masked", "locked",
             "pseudonym", "source"}
CHAT_KEYS = {"answer_with_pseudonyms", "outbound_text", "identifier_count"}
LABELS = {"Person", "PHN", "MRN", "License", "Address", "Phone", "Email", "Date", "Age", "Location description",
          "Unique role", "Family detail", "Employer", "Person description", "Drug", "Dose", "Diagnosis", "Lab value"}

sent_to_gemini: list[tuple[str, str]] = []


def fake_ask(note, history, question):
    sent_to_gemini.append((note, question))
    return "Referral for [PATIENT_01] (PATIENT_1) seen by [PROVIDER_01]. [PATIENT_07] is unknown."


def client():
    use_fake_gliner(GLINER_PHRASES)
    gemini_client.ask = fake_ask
    config.GEMINI_API_KEY = "test-key"
    return app_module.app.test_client()


def new_doc(c, text=NOTE, title="Visit note"):
    r = c.post("/documents", json={"title": title, "text": text})
    assert r.status_code == 201, r.json
    return r.json


def check_doc(doc):
    assert set(doc) == DOC_KEYS, set(doc) ^ DOC_KEYS
    assert isinstance(doc["id"], str) and doc["id"]
    assert isinstance(doc["title"], str) and doc["title"]
    assert doc["source"] in ("pdf", "paste")
    assert isinstance(doc["original_text"], str)
    assert doc["pseudonymized_text"] is None or isinstance(doc["pseudonymized_text"], str)
    assert doc["status"] in ("needs_review", "ready")
    datetime.fromisoformat(doc["created_at"])
    prev_end = 0
    for i, f in enumerate(doc["flags"]):
        assert set(f) == FLAG_KEYS, set(f) ^ FLAG_KEYS
        assert f["flag_code"] == f"F{i + 1}"
        assert isinstance(f["start_idx"], int) and isinstance(f["end_idx"], int)
        assert prev_end <= f["start_idx"] < f["end_idx"] <= len(doc["original_text"]), "flags overlap or unsorted"
        assert doc["original_text"][f["start_idx"]:f["end_idx"]] == f["text"]
        assert f["label"] in LABELS, f["label"]
        assert f["tier"] in ("high", "med", "low")
        assert isinstance(f["reason"], str) and f["reason"]
        assert isinstance(f["masked"], bool) and isinstance(f["locked"], bool)
        assert f["locked"] == (f["tier"] == "high")
        assert not f["locked"] or f["masked"], "a locked flag must be masked"
        assert f["source"] in ("presidio", "model", "lexicon")
        assert f["pseudonym"].startswith("[") and f["pseudonym"].endswith("]") and f["pseudonym"] != "[NAME]"
        prev_end = f["end_idx"]


def flag(doc, text):
    return next(f for f in doc["flags"] if f["text"] == text)


# ---------- POST /documents ----------

def test_paste_returns_a_doc():
    c = client()
    doc = new_doc(c)
    check_doc(doc)
    assert doc["source"] == "paste" and doc["status"] == "needs_review" and doc["pseudonymized_text"] is None
    assert doc["title"] == "Visit note" and doc["original_text"] == NOTE


def test_default_tiers_and_locks():
    c = client()
    doc = new_doc(c)
    assert flag(doc, "Margaret Ellison")["tier"] == "high" and flag(doc, "Margaret Ellison")["pseudonym"] == "[PATIENT_01]"
    assert flag(doc, "Dr. Raj Patel")["pseudonym"].startswith("[PROVIDER_")
    assert flag(doc, "9123 947 241")["label"] == "PHN" and flag(doc, "9123 947 241")["pseudonym"].startswith("[HCN_")
    assert flag(doc, "bush pilot")["tier"] == "med" and not flag(doc, "bush pilot")["locked"]
    assert all(f["masked"] for f in doc["flags"] if f["tier"] != "low")


def test_paste_title_defaults():
    c = client()
    assert c.post("/documents", json={"text": NOTE}).json["title"] == "Pasted note"
    assert c.post("/documents", json={"title": "   ", "text": NOTE}).json["title"] == "Pasted note"


def test_pdf_upload_returns_a_doc():
    c = client()
    r = c.post("/documents", data={"file": (io.BytesIO(build_pdf([["Pt Margaret Ellison from Tofino."]])), "Referral.PDF")},
               content_type="multipart/form-data")
    assert r.status_code == 201, r.json
    check_doc(r.json)
    assert r.json["source"] == "pdf" and r.json["title"] == "Referral"


def test_bad_create_requests():
    c = client()
    for body in [None, {}, {"text": 5}, {"text": ["a"]}, {"title": "x"}]:
        r = c.post("/documents", json=body) if body is not None else c.post("/documents", data="nope")
        assert r.status_code == 400 and isinstance(r.json["detail"], str), body
    assert c.post("/documents", json={"text": "   \n "}).status_code == 400
    assert c.post("/documents", json={"text": "a " * 150_000}).status_code == 413


def test_same_value_same_pseudonym_across_documents():
    c = client()
    a = new_doc(c)
    b = new_doc(c, text="Follow-up for Margaret Ellison in Tofino.")
    assert flag(a, "Margaret Ellison")["pseudonym"] == flag(b, "Margaret Ellison")["pseudonym"]
    assert flag(a, "Tofino")["pseudonym"] == flag(b, "Tofino")["pseudonym"]


# ---------- GET ----------

def test_list_and_get():
    c = client()
    a = new_doc(c, title="First")
    b = new_doc(c, title="Second")
    listed = c.get("/documents").json
    for d in listed:
        check_doc(d)
    ids = [d["id"] for d in listed]
    assert ids.index(b["id"]) < ids.index(a["id"]), "newest first"
    assert c.get(f"/documents/{a['id']}").json == a
    assert c.get("/documents/doc-nope").status_code == 404


# ---------- PATCH flags ----------

def test_locked_high_flag_returns_403():
    c = client()
    doc = new_doc(c)
    high = flag(doc, "Margaret Ellison")
    for masked in (False, True):
        r = c.patch(f"/documents/{doc['id']}/flags/{high['flag_code']}", json={"masked": masked})
        assert r.status_code == 403 and isinstance(r.json["detail"], str)
    assert flag(c.get(f"/documents/{doc['id']}").json, "Margaret Ellison")["masked"] is True


def test_med_flag_toggles_and_resets_review():
    c = client()
    doc = new_doc(c)
    c.post(f"/documents/{doc['id']}/finalize")
    med = flag(doc, "bush pilot")
    r = c.patch(f"/documents/{doc['id']}/flags/{med['flag_code']}", json={"masked": False})
    assert r.status_code == 200
    check_doc(r.json)
    assert flag(r.json, "bush pilot")["masked"] is False
    assert r.json["status"] == "needs_review" and r.json["pseudonymized_text"] is None
    r = c.patch(f"/documents/{doc['id']}/flags/{med['flag_code']}", json={"masked": True})
    assert flag(r.json, "bush pilot")["masked"] is True


def test_bad_patch_requests():
    c = client()
    doc = new_doc(c)
    code = flag(doc, "bush pilot")["flag_code"]
    for body in [None, {}, {"masked": "false"}, {"masked": 0}, {"masked": None}]:
        r = c.patch(f"/documents/{doc['id']}/flags/{code}", json=body) if body is not None \
            else c.patch(f"/documents/{doc['id']}/flags/{code}", data="x")
        assert r.status_code == 400, body
    assert c.patch(f"/documents/doc-nope/flags/{code}", json={"masked": False}).status_code == 404
    assert c.patch(f"/documents/{doc['id']}/flags/F999", json={"masked": False}).status_code == 404


def test_patch_calls_audit_with_decisions_only():
    calls = []

    class FakeAudit:
        @staticmethod
        def log_flag_change(**kw):
            calls.append(kw)

    app_module.audit = FakeAudit
    try:
        c = client()
        doc = new_doc(c)
        med = flag(doc, "bush pilot")
        c.patch(f"/documents/{doc['id']}/flags/{med['flag_code']}", json={"masked": False})
        c.patch(f"/documents/{doc['id']}/flags/{flag(doc, 'Margaret Ellison')['flag_code']}", json={"masked": False})
    finally:
        app_module.audit = None
    assert len(calls) == 1, "the refused HIGH change must not be logged as a change"
    kw = calls[0]
    assert set(kw) == {"document_id", "flag_code", "label", "tier", "default_masked", "final_masked", "changed_by"}
    assert kw["tier"] == "med" and kw["default_masked"] is True and kw["final_masked"] is False
    assert "bush" not in repr(kw).lower(), "audit must never receive text"


def test_broken_audit_never_breaks_a_request():
    class BrokenAudit:
        @staticmethod
        def log_flag_change(**kw):
            raise RuntimeError("snowflake down")

    app_module.audit = BrokenAudit
    try:
        c = client()
        doc = new_doc(c)
        r = c.patch(f"/documents/{doc['id']}/flags/{flag(doc, 'bush pilot')['flag_code']}", json={"masked": False})
        assert r.status_code == 200
    finally:
        app_module.audit = None


# ---------- finalize and mapping ----------

def test_finalize_masks_every_masked_value():
    c = client()
    doc = new_doc(c)
    r = c.post(f"/documents/{doc['id']}/finalize")
    assert r.status_code == 200
    check_doc(r.json)
    assert r.json["status"] == "ready"
    out = r.json["pseudonymized_text"]
    for f in r.json["flags"]:
        if f["masked"]:
            assert f["text"].lower() not in out.lower(), f"leaked {f['flag_code']}"
            assert f["pseudonym"] in out
    assert "Parkinson's" in out and "nitrofurantoin 100 mg BID x 7 days" in out


def test_finalize_keeps_unmasked_med_values():
    c = client()
    doc = new_doc(c)
    c.patch(f"/documents/{doc['id']}/flags/{flag(doc, '74-year-old')['flag_code']}", json={"masked": False})
    out = c.post(f"/documents/{doc['id']}/finalize").json["pseudonymized_text"]
    assert "74-year-old" in out


def test_mapping_is_masked_flags_only():
    c = client()
    doc = new_doc(c)
    c.patch(f"/documents/{doc['id']}/flags/{flag(doc, '74-year-old')['flag_code']}", json={"masked": False})
    m = c.get(f"/documents/{doc['id']}/mapping").json
    assert m[flag(doc, "Margaret Ellison")["pseudonym"]] == "Margaret Ellison"
    assert "74-year-old" not in m.values()
    assert all(k.startswith("[") for k in m)
    assert c.get("/documents/doc-nope/mapping").status_code == 404
    assert c.post("/documents/doc-nope/finalize").status_code == 404


# ---------- chat ----------

def ready_doc(c, text=NOTE):
    doc = new_doc(c, text=text)
    return c.post(f"/documents/{doc['id']}/finalize").json


def test_chat_returns_chat_response():
    c = client()
    sent_to_gemini.clear()
    doc = ready_doc(c)
    r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "Draft a referral letter to cardiology."})
    assert r.status_code == 200, r.json
    assert set(r.json) == CHAT_KEYS
    assert r.json["identifier_count"] == 0
    assert r.json["answer_with_pseudonyms"].startswith("Referral for [PATIENT_01]")
    assert r.json["outbound_text"].startswith("Document 1:\n") and "Request: Draft a referral" in r.json["outbound_text"]
    note, question = sent_to_gemini[-1]
    assert note in r.json["outbound_text"] and question in r.json["outbound_text"]


def test_chat_over_several_documents():
    c = client()
    a, b = ready_doc(c), ready_doc(c, text="Second visit: Margaret Ellison improving.")
    r = c.post("/chat", json={"document_ids": [a["id"], b["id"]], "message": "Summarize both"})
    assert "Document 1:" in r.json["outbound_text"] and "Document 2:" in r.json["outbound_text"]
    assert "Ellison" not in r.json["outbound_text"]


def test_chat_requires_finalized_documents():
    c = client()
    doc = new_doc(c)
    assert c.post("/chat", json={"document_ids": [doc["id"]], "message": "hi"}).status_code == 409


def test_bad_chat_requests():
    c = client()
    doc = ready_doc(c)
    for body in [None, {}, {"document_ids": [], "message": "hi"}, {"document_ids": doc["id"], "message": "hi"},
                 {"document_ids": [doc["id"]]}, {"document_ids": [doc["id"]], "message": "  "},
                 {"document_ids": [5], "message": "hi"}]:
        r = c.post("/chat", json=body) if body is not None else c.post("/chat", data="x")
        assert r.status_code == 400, body
    assert c.post("/chat", json={"document_ids": ["doc-nope"], "message": "hi"}).status_code == 404


def test_chat_without_gemini_key_is_a_clear_error():
    c = client()
    doc = ready_doc(c)
    config.GEMINI_API_KEY = ""
    try:
        r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "hi"})
    finally:
        config.GEMINI_API_KEY = "test-key"
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json["detail"]


def test_gemini_failure_is_a_clean_502():
    c = client()
    doc = ready_doc(c)

    def boom(*a):
        raise ConnectionError("network down")

    gemini_client.ask = boom
    r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "hi"})
    assert r.status_code == 502 and "network" not in r.json["detail"]


def test_chat_calls_audit_with_counts_only():
    calls = []

    class FakeAudit:
        @staticmethod
        def log_outbound(**kw):
            calls.append(kw)

    app_module.audit = FakeAudit
    try:
        c = client()
        doc = ready_doc(c)
        c.post("/chat", json={"document_ids": [doc["id"]], "message": "hi"})
        c.post("/chat", json={"document_ids": [doc["id"]], "message": "email jo.doe@example.com"})   # blocked
    finally:
        app_module.audit = None
    assert len(calls) == 1, "only messages actually sent are logged"
    assert set(calls[0]) == {"document_ids", "word_count", "identifier_count", "model"}
    assert isinstance(calls[0]["word_count"], int) and calls[0]["identifier_count"] == 0


# ---------- misc ----------

def test_health():
    r = client().get("/health").json
    assert r["ok"] is True and r["lexicon"] in ("tidb", "csv", "off")


def test_cors_preflight_for_the_frontend():
    c = client()
    r = c.open("/documents/x/flags/F1", method="OPTIONS", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "PATCH"})
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "PATCH" in r.headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in r.headers["Access-Control-Allow-Headers"]


def test_store_is_memory_only():
    # A restart is a fresh process: DOCS is a plain dict, so a new process starts empty.
    assert isinstance(app_module.DOCS, dict)
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-W", "ignore", "-c", "import app; print(len(app.DOCS))"],
                         capture_output=True, text=True, env={**__import__("os").environ, "USE_GLINER": "0"})
    assert out.stdout.strip().splitlines()[-1] == "0", out.stdout + out.stderr


if __name__ == "__main__":
    run(globals())
