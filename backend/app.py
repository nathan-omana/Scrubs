"""
Flask backend (CLAUDE.md section 10). Response shapes match lib/types.ts: Doc, Flag, ChatResponse.

Documents, flags and mappings live ONLY in this process's memory (the DOCS dict below).
Nothing is written to disk or any database, and a restart clears everything.

Endpoints
  GET    /health
  POST   /documents                         PDF upload (multipart "file") or JSON {title, text} -> Doc (201)
  GET    /documents                         -> [Doc], newest first
  GET    /documents/<id>                    -> Doc
  PATCH  /documents/<id>/flags/<flag_code>  {masked} -> Doc   (403 for locked HIGH flags)
  POST   /documents/<id>/finalize           -> Doc with pseudonymized_text, status "ready"
  GET    /documents/<id>/mapping            -> {pseudonym: real value} for client re-identification
  POST   /chat                              {document_ids, message} -> ChatResponse

Errors are JSON {"detail": "message safe to show the user"}.

Run:  cd backend && python app.py      (http://127.0.0.1:5000)
"""
import io
import logging
import random
import re
import uuid
from datetime import datetime, timezone

from flask import Flask, Request, jsonify, request

import config
import gemini_client
import pipeline
from pipeline import lexicon, rules, tagging
from pipeline.dates import shift_date
from pipeline.extract import PdfError, ScannedPdfError, extract_text

try:
    import audit          # Snowflake audit hooks (backend/audit.py, Nathan's lane)
except ImportError:       # not merged yet: decisions simply aren't logged
    audit = None


class InMemoryRequest(Request):
    """
    By default Flask/Werkzeug writes uploads bigger than 500 KB to a TEMP FILE ON DISK.
    We promised "never stored", so force every upload to stay in memory.
    """
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return io.BytesIO()


app = Flask(__name__)
app.request_class = InMemoryRequest
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024  # reject huge uploads

# Our log lines contain COUNTS ONLY, never note text. Don't add print(text) while debugging.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("scrubin")

# ---------- In-memory store (cleared on restart) ----------
DOCS: dict[str, dict] = {}                 # id -> doc, flags keep internal fields (type, found_by)
PSEUDONYMS = tagging.Pseudonyms()          # same real value -> same pseudonym across all documents
# Masked dates move back by this many days (CLAUDE.md section 8), so intervals stay correct.
# One offset per process, not per document: the same real date always becomes the same shifted
# date, across documents too, so merged mappings in the browser never disagree. For the
# single-patient demo this is "one offset per patient". Memory only: never logged or sent.
DATE_OFFSET_DAYS = -random.SystemRandom().randint(20, 90)

DOC_FIELDS = ("id", "title", "source", "original_text", "pseudonymized_text", "status", "created_at", "flags")
FLAG_FIELDS = ("flag_code", "start_idx", "end_idx", "text", "label", "tier", "reason", "masked", "locked",
               "pseudonym", "source")


def public(doc: dict) -> dict:
    """The Doc exactly as lib/types.ts defines it (internal fields removed)."""
    out = {k: doc[k] for k in DOC_FIELDS if k != "flags"}
    out["flags"] = [{k: f[k] for k in FLAG_FIELDS} for f in doc["flags"]]
    return out


def error(message: str, status: int):
    return jsonify(detail=message), status


def get_doc(doc_id: str) -> dict | None:
    return DOCS.get(doc_id)


def call_audit(name: str, **kwargs) -> None:
    """Audit hooks get decisions and counts only, never text, and must never break a request."""
    fn = getattr(audit, name, None) if audit else None
    if fn:
        try:
            fn(**kwargs)
        except Exception as e:
            log.info("audit: %s failed (%s)", name, type(e).__name__)


def date_pseudonym(value: str, text: str) -> str | None:
    """
    The shifted date for a DATE flag, or None to use a [DATE_NN] pseudonym instead: when the date
    can't be read, or when the shifted date is also written somewhere in this note. That clash
    would make the leak check see a real date in the outbound text and mix up re-identification.
    """
    shifted = shift_date(value, DATE_OFFSET_DAYS)
    if not shifted or re.search(r"(?<!\w)" + re.escape(shifted) + r"(?!\w)", text, re.IGNORECASE):
        return None
    return shifted


def word_count(text: str) -> int:
    return len(text.split())


@app.after_request
def allow_frontend(resp):
    # CORS: only the frontend's origin may call us from a browser (CLAUDE.md section 14, rule 7).
    # Any other website gets no CORS header, so the browser blocks it from reading responses.
    origin = request.headers.get("Origin")
    if origin in config.FRONTEND_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
    resp.headers["Vary"] = "Origin"
    return resp


@app.errorhandler(413)
def too_large(_e):
    return error(f"File is larger than {config.MAX_UPLOAD_MB} MB.", 413)


@app.get("/health")
def health():
    return {"ok": True, "gliner": config.USE_GLINER, "lexicon": lexicon.load()}  # "tidb" | "csv" | "off"


@app.post("/documents")
def create_document():
    if "file" in request.files:
        f = request.files["file"]
        name = f.filename or "Uploaded file"
        try:
            text = extract_text(name, f.read())
        except ScannedPdfError as e:          # no text layer: say so, so the user can paste instead
            return error(str(e), 422)
        except PdfError as e:                 # not a PDF, damaged, password protected, too many pages
            return error(str(e), 400)
        is_pdf = name.lower().endswith(".pdf")
        title = re.sub(r"\.(pdf|txt|docx)$", "", name, flags=re.IGNORECASE) or "Uploaded file"
        source = "pdf" if is_pdf else "paste"
    else:
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            return error("Send a PDF as multipart/form-data, or JSON with a 'text' field.", 400)
        text = body["text"]
        title = (body.get("title") or "").strip() if isinstance(body.get("title"), str) else ""
        title = title or "Pasted note"
        source = "paste"

    if not text.strip():
        return error("The note text is empty.", 400)
    if len(text) > config.MAX_TEXT_CHARS:
        return error(f"Document too long (max {config.MAX_TEXT_CHARS:,} characters).", 413)

    flags = pipeline.analyze(text)
    for f in flags:
        f["pseudonym"] = date_pseudonym(f["text"], text) if f["type"] == "DATE" else None
        f["pseudonym"] = f["pseudonym"] or PSEUDONYMS.get(config.TYPES[f["type"]][2], f["text"])

    doc = {
        "id": f"doc-{uuid.uuid4().hex[:12]}",
        "title": title,
        "source": source,
        "original_text": text,
        "pseudonymized_text": None,
        "status": "needs_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "flags": flags,
    }
    DOCS[doc["id"]] = doc
    log.info("document created: %d chars | %s", len(text), pipeline.summary(flags))
    return jsonify(public(doc)), 201


@app.get("/documents")
def list_documents():
    docs = sorted(DOCS.values(), key=lambda d: d["created_at"], reverse=True)
    return jsonify([public(d) for d in docs])


@app.get("/documents/<doc_id>")
def get_document(doc_id):
    doc = get_doc(doc_id)
    return jsonify(public(doc)) if doc else error("Document not found.", 404)


@app.patch("/documents/<doc_id>/flags/<flag_code>")
def set_flag(doc_id, flag_code):
    doc = get_doc(doc_id)
    if not doc:
        return error("Document not found.", 404)
    flag = next((f for f in doc["flags"] if f["flag_code"] == flag_code), None)
    if not flag:
        return error("Flag not found.", 404)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("masked"), bool):
        return error("Send JSON {\"masked\": true} or {\"masked\": false}.", 400)
    if flag["locked"]:                                    # enforced here, not just in the UI
        return error("HIGH items are always masked.", 403)

    flag["masked"] = body["masked"]
    doc["status"], doc["pseudonymized_text"] = "needs_review", None    # must be finalized again
    call_audit("log_flag_change", document_id=doc_id, flag_code=flag_code, label=flag["label"],
               tier=flag["tier"], default_masked=flag["tier"] != "low", final_masked=flag["masked"],
               changed_by=config.CLINICIAN)
    log.info("flag change: tier=%s masked=%s", flag["tier"], flag["masked"])
    return jsonify(public(doc))


@app.post("/documents/<doc_id>/finalize")
def finalize(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return error("Document not found.", 404)
    doc["pseudonymized_text"] = tagging.pseudonymize(doc["original_text"], doc["flags"])
    doc["status"] = "ready"
    log.info("finalized: %d masked, %d kept",
             sum(f["masked"] for f in doc["flags"]), sum(not f["masked"] for f in doc["flags"]))
    return jsonify(public(doc))


@app.get("/documents/<doc_id>/mapping")
def mapping(doc_id):
    doc = get_doc(doc_id)
    return jsonify(tagging.mapping_of(doc["flags"])) if doc else error("Document not found.", 404)


def leak_check(outbound: str, flags: list[dict]) -> tuple[int, str]:
    """
    (count, reason): how many masked original values (whole word, any case) are still in the
    outbound text, plus 1 for a raw PHN or email anywhere. The reason names KINDS only
    ("Person, PHN"), never the values, because it is shown on screen and may be logged.
    It checks exactly the values pseudonymize() replaces everywhere (config.MIN_REPEAT_CHARS),
    so its own hiding step can never trip it.
    """
    leaked: dict[str, str] = {}                                   # value -> label
    for f in flags:
        v = f["text"].strip().lower()
        if (f["masked"] and len(v) >= config.MIN_REPEAT_CHARS
                and re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", outbound, re.IGNORECASE)):
            leaked.setdefault(v, f["label"])
    reasons = []
    if leaked:
        kinds = ", ".join(sorted(set(leaked.values())))
        reasons.append(f"{len(leaked)} masked value{'s' if len(leaked) != 1 else ''} still in the text ({kinds})")
    raw = rules.looks_unsafe(outbound)                            # "raw PHN found" / "raw email found"
    if raw:
        reasons.append("a PHN in the message that isn't in any reviewed document" if "PHN" in raw
                       else "an email address in the message that isn't in any reviewed document")
    return len(leaked) + (1 if raw else 0), "; ".join(reasons).capitalize() if reasons else ""


@app.post("/chat")
def chat():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("Send JSON {document_ids, message}.", 400)
    ids, message = body.get("document_ids"), body.get("message")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        return error("Select at least one document.", 400)
    if not isinstance(message, str) or not message.strip():
        return error("The message is empty.", 400)
    docs = [get_doc(i) for i in ids]
    if any(d is None for d in docs):
        return error("Document not found.", 404)
    if any(d["status"] != "ready" for d in docs):
        return error("Finish reviewing every selected document before chatting.", 409)

    # Tag anything identifying the clinician typed, using every selected document's mapping.
    flags = [f for d in docs for f in d["flags"]]
    safe_message = tagging.tag_question(message, tagging.mapping_of(flags))
    note = "\n\n".join(f"Document {i + 1}:\n{d['pseudonymized_text']}" for i, d in enumerate(docs))
    outbound_text = f"{note}\n\nRequest: {safe_message}"

    # Leak check: never send if an original masked value (or a raw PHN/email) is still present.
    identifier_count, reason = leak_check(outbound_text, flags)
    if identifier_count:
        log.info("chat blocked: %d identifiers found", identifier_count)
        return jsonify(answer_with_pseudonyms="", outbound_text=outbound_text, identifier_count=identifier_count,
                       blocked_reason=reason)

    if not config.GEMINI_API_KEY:
        return error("Gemini isn't set up. Add GEMINI_API_KEY to .env and restart the backend.", 503)
    try:
        answer = gemini_client.ask(note, [], safe_message)
    except Exception as e:
        log.info("chat: Gemini error (%s)", type(e).__name__)
        return error("Gemini request failed. Try again.", 502)

    call_audit("log_outbound", document_ids=ids, word_count=word_count(outbound_text),
               identifier_count=0, model=config.GEMINI_MODEL)
    log.info("chat: sent %d words, 0 identifiers", word_count(outbound_text))
    return jsonify(answer_with_pseudonyms=answer, outbound_text=outbound_text, identifier_count=0)


if __name__ == "__main__":
    # 127.0.0.1 = only this computer can reach it. Don't change to 0.0.0.0 unless you mean it.
    # On a Mac, AirPlay Receiver also listens on 5000: call us at 127.0.0.1:5000 (not localhost),
    # or set PORT=5001 in .env and point NEXT_PUBLIC_API_URL there.
    app.run(host="127.0.0.1", port=config.PORT, debug=False)
