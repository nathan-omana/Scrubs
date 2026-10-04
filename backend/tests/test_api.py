"""
The section 10 API, checked against the frontend contract in lib/types.ts (Doc, Flag, ChatResponse).
GLiNER and Gemini are faked. Run from the backend folder:   python -m tests.test_api
"""
import io
from datetime import date, datetime, timedelta

import app as app_module
import config
import gemini_client
from pipeline.dates import shift_date
from tests._util import run, use_fake_gliner
from tests.pdf_factory import build_pdf
from tests.samples import DEMO_NOTE

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
        if f["label"] == "Date" and not f["pseudonym"].startswith("["):
            assert f["pseudonym"] != f["text"], "a shifted date must differ from the real one"
        else:
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
    dates = {f["pseudonym"] for f in doc["flags"] if f["label"] == "Date"}
    assert all(k.startswith("[") or k in dates for k in m)
    assert c.get("/documents/doc-nope/mapping").status_code == 404
    assert c.post("/documents/doc-nope/finalize").status_code == 404


# ---------- date shifting ----------

def test_dates_are_shifted_not_tagged():
    # CLAUDE.md section 12 note: "Sept 28" becomes a date moved by the session's offset.
    c = client()
    doc = new_doc(c, text=DEMO_NOTE)
    check_doc(doc)
    sept = flag(doc, "Sept 28")
    assert sept["pseudonym"] == shift_date("Sept 28", app_module.DATE_OFFSET_DAYS)
    assert -90 <= app_module.DATE_OFFSET_DAYS <= -20
    out = c.post(f"/documents/{doc['id']}/finalize").json["pseudonymized_text"]
    assert "Sept 28" not in out and sept["pseudonym"] in out
    assert c.get(f"/documents/{doc['id']}/mapping").json[sept["pseudonym"]] == "Sept 28"


def test_shifted_dates_keep_intervals():
    c = client()
    doc = new_doc(c, text="Admitted 2026-09-21. Discharged 2026-09-28. Seen again on 2026-10-12.")
    days = [date.fromisoformat(flag(doc, d)["pseudonym"]) for d in ("2026-09-21", "2026-09-28", "2026-10-12")]
    assert (days[1] - days[0]).days == 7 and (days[2] - days[1]).days == 14
    assert days[0] == date(2026, 9, 21) + timedelta(app_module.DATE_OFFSET_DAYS)


def test_unreadable_or_clashing_date_falls_back_to_a_tag():
    assert app_module.date_pseudonym("Sept 28 at 10:00", "Sept 28 at 10:00") is None
    old = app_module.DATE_OFFSET_DAYS
    app_module.DATE_OFFSET_DAYS = -7       # 2026-09-28 would become 2026-09-21, a real date in the note
    try:
        c = client()
        doc = new_doc(c, text="Pt Margaret Ellison seen 2026-09-21 and 2026-09-28 for cough.")
        assert flag(doc, "2026-09-28")["pseudonym"].startswith("[DATE_")
        assert flag(doc, "2026-09-21")["pseudonym"] == "2026-09-14"
        c.post(f"/documents/{doc['id']}/finalize")
        sent_to_gemini.clear()
        r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "What happened on 2026-09-28?"})
        assert r.json["identifier_count"] == 0, r.json            # the leak check still passes
        assert "2026-09-21" not in r.json["outbound_text"] and "2026-09-28" not in r.json["outbound_text"]
    finally:
        app_module.DATE_OFFSET_DAYS = old


def test_same_day_in_other_formats_is_shifted_too():
    c = client()
    sent_to_gemini.clear()
    doc = ready_doc(c, text="Pt Margaret Ellison admitted September 21, 2026 and again on Sep 28. Seen 28 Sept.")
    out = doc["pseudonymized_text"]
    for raw in ["September 21", "Sep 28", "28 Sept"]:
        assert raw not in out, (raw, out)
    sep28 = shift_date("Sep 28", app_module.DATE_OFFSET_DAYS)
    for q in ["what about september 28?", "and 28 Sept?", "Sept. 28th"]:
        r = c.post("/chat", json={"document_ids": [doc["id"]], "message": q})
        assert r.json["identifier_count"] == 0, (q, r.json)
        assert sep28 in sent_to_gemini[-1][1] and "28" not in sent_to_gemini[-1][1].replace(sep28, ""), sent_to_gemini[-1]


def test_unrelated_dates_in_chat_are_left_alone():
    c = client()
    sent_to_gemini.clear()
    doc = ready_doc(c, text=DEMO_NOTE)
    c.post("/chat", json={"document_ids": [doc["id"]], "message": "Book a visit on Oct 30"})
    assert sent_to_gemini[-1][1] == "Book a visit on Oct 30"


def test_shifted_day_written_another_way_in_the_note_falls_back_to_a_tag():
    old = app_module.DATE_OFFSET_DAYS
    app_module.DATE_OFFSET_DAYS = -7            # Sept 28 -> Sept 21, which the note mentions as "21 September"
    try:
        c = client()
        doc = ready_doc(c, text="Pt Margaret Ellison seen 21 September and Sept 28.")
        assert flag(doc, "Sept 28")["pseudonym"].startswith("[DATE_")
        r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "Summarize"})
        assert r.json["identifier_count"] == 0, r.json
    finally:
        app_module.DATE_OFFSET_DAYS = old


def test_pain_scores_stay_and_bare_dates_still_shift():
    c = client()
    doc = ready_doc(c, text="Pt Margaret Ellison seen on 9/10 for follow-up. Pain 7/10 at rest, power 4/5.")
    out = doc["pseudonymized_text"]
    assert "Pain 7/10 at rest, power 4/5." in out, out
    assert "9/10" not in out and flag(doc, "9/10")["pseudonym"] == shift_date("9/10", app_module.DATE_OFFSET_DAYS)


def test_chat_sends_shifted_dates_only():
    c = client()
    sent_to_gemini.clear()
    doc = ready_doc(c, text=DEMO_NOTE)
    r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "What happened on Sept 28?"})
    assert r.json["identifier_count"] == 0, r.json
    shifted = flag(doc, "Sept 28")["pseudonym"]
    note, question = sent_to_gemini[-1]
    assert "Sept 28" not in note + question and shifted in note and shifted in question


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


def test_blocked_chat_says_why_without_values():
    c = client()
    doc = ready_doc(c, text="Pt seen for cough. Apixaban 5 mg BID.")
    r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "Send it to jo.doe@example.com"})
    assert r.status_code == 200
    assert set(r.json) == CHAT_KEYS | {"blocked_reason"}
    assert r.json["identifier_count"] == 1 and r.json["answer_with_pseudonyms"] == ""
    assert "email" in r.json["blocked_reason"] and "jo.doe" not in r.json["blocked_reason"]


def test_leak_check_never_trips_on_its_own_hiding_step():
    # Short masked values (like a "2" wrongly flagged as a date) are only replaced where flagged,
    # so the leak check must not look for them elsewhere. This blocked every message on a quiz PDF.
    text = "2. Question one. 3. Question two, answer 2. Pt Margaret Ellison in Tofino."

    def flag(value, label, pseudonym):
        start = text.index(value)
        return {"start_idx": start, "end_idx": start + len(value), "text": value, "masked": True,
                "label": label, "pseudonym": pseudonym}

    flags = [flag("2", "Date", "[DATE_01]"), flag("3", "Date", "[DATE_02]"),
             flag("Margaret Ellison", "Person", "[PATIENT_01]")]
    from pipeline import tagging
    out = tagging.pseudonymize(text, flags)
    assert app_module.leak_check(out, flags) == (0, "")
    assert app_module.leak_check(out + " Margaret Ellison", flags)[0] == 1   # a real leak still blocks


OKAFOR_NOTE = ("Daniel Okafor, PHN 9487 312 652, seen by Dr. Priya Sandhu. Phone (604) 555-0187. "
               "Mr. Okafor reports chest pain. Sandhu to follow up; call 604-555-0187.")
OKAFOR_PHRASES = {"Daniel Okafor": "person name", "Dr. Priya Sandhu": "doctor"}


def okafor_doc(c):
    use_fake_gliner(OKAFOR_PHRASES)
    doc = c.post("/documents", json={"title": "t", "text": OKAFOR_NOTE}).json
    assert {"Daniel Okafor", "Dr. Priya Sandhu", "(604) 555-0187"} <= {f["text"] for f in doc["flags"]}, doc["flags"]
    return c.post(f"/documents/{doc['id']}/finalize").json


def test_name_and_number_variants_never_reach_gemini():
    c = client()
    doc = okafor_doc(c)
    out = doc["pseudonymized_text"]
    for secret in ["Okafor", "Daniel", "Sandhu", "Priya", "555-0187", "9487"]:
        assert secret not in out, (secret, out)
    for message in ["Summarize Mr. Okafor's case", "Patient Okafor, Daniel - summarize", "Was Dr. Sandhu involved?",
                    "Call 604-555-0187", "Call 6045550187", "PHN 9487312652"]:
        sent_to_gemini.clear()
        r = c.post("/chat", json={"document_ids": [doc["id"]], "message": message})
        assert r.status_code == 200 and r.json["identifier_count"] == 0, (message, r.json)
        note, question = sent_to_gemini[-1]
        for secret in ["okafor", "daniel", "sandhu", "6045550187", "555-0187", "9487312652"]:
            assert secret not in (note + question).lower(), (message, question)


def test_leak_check_catches_variants_but_not_its_own_output():
    c = client()
    doc = okafor_doc(c)
    flags = app_module.DOCS[doc["id"]]["flags"]
    assert app_module.leak_check(doc["pseudonymized_text"], flags) == (0, "")
    for leak in ["Mr. Okafor", "okafor's", "6045550187", "604 555 0187"]:
        assert app_module.leak_check(doc["pseudonymized_text"] + " " + leak, flags)[0] >= 1, leak


def test_blocked_reason_keeps_upper_case_kinds():
    c = client()
    doc = okafor_doc(c)
    r = c.post("/chat", json={"document_ids": [doc["id"]], "message": "Also add PHN 9123 947 241."})
    assert r.json["identifier_count"] == 1 and "PHN" in r.json["blocked_reason"], r.json
    flags = app_module.DOCS[doc["id"]]["flags"]
    reason = app_module.leak_check("Daniel Okafor", flags)[1]
    assert reason[0].isdigit() and "masked value" in reason and "(Person)" in reason, reason


def test_rule_address_and_license_are_locked_high():
    c = client()
    doc = new_doc(c, text="Pt lives at 4820 Marine Ave. Rx signed, CPSBC #34567.")
    for value, label in [("4820 Marine Ave", "Address"), ("34567", "License")]:
        f = next(f for f in doc["flags"] if f["text"].startswith(value))
        assert f["label"] == label and f["tier"] == "high" and f["locked"] and f["source"] == "presidio", f


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


class FlakyGenai:
    """Fails with the given HTTP codes first, then answers. Records which model each call used."""

    def __init__(self, codes):
        self.codes, self.models_used = list(codes), []
        self.models = self

    def generate_content(self, model, contents, config):
        self.models_used.append(model)
        if self.codes:
            err = Exception("gemini error")
            err.code = self.codes.pop(0)
            raise err
        return type("R", (), {"text": "Recovered answer for [PATIENT_01]."})()


def test_gemini_busy_errors_retry_then_fall_back():
    import importlib
    gc = importlib.reload(gemini_client)          # the real ask(), not the fake set by client()
    gc.RETRY_WAIT_SECONDS = 0
    old = (gc._client, config.GEMINI_MODEL, config.GEMINI_FALLBACK_MODELS)
    config.GEMINI_MODEL, config.GEMINI_FALLBACK_MODELS = "main", ["backup1", "backup2"]
    try:
        gc._client = FlakyGenai([503])                       # busy once: retry the same model
        assert gc.ask("note", [], "hi").startswith("Recovered") and gc._client.models_used == ["main", "main"]
        assert gc.last_model == "main"
        gc._client = FlakyGenai([503, 503])                  # main stays busy: fall back
        gc.ask("note", [], "hi")
        assert gc._client.models_used == ["main", "main", "backup1"] and gc.last_model == "backup1"
        gc._client = FlakyGenai([503] * 6)                   # everything busy: give up with the 503
        assert raises_with_code(gc, 503) and len(gc._client.models_used) == 6
        gc._client = FlakyGenai([404])                       # wrong model or key: no retry, no fallback
        assert raises_with_code(gc, 404) and gc._client.models_used == ["main"]
    finally:
        gc._client, config.GEMINI_MODEL, config.GEMINI_FALLBACK_MODELS = old


def raises_with_code(gc, code):
    try:
        gc.ask("note", [], "hi")
    except Exception as e:
        return getattr(e, "code", None) == code
    return False


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
