"""
Flask backend. Stateless: it keeps NOTHING between requests.

Endpoints
  POST /analyze  file upload (or JSON {"text": ...}) -> text + flagged spans + risk level
  POST /tag      {"text", "spans", "remove_ids"}    -> tagged text + mapping (mapping goes back to the browser)
  POST /chat     {"tagged_note", "history", "question"} -> Gemini's (still tagged) answer

Run:  cd backend && python app.py      (http://127.0.0.1:5000)
"""
import io
import logging

from flask import Flask, Request, jsonify, request

import config
import gemini_client
import pipeline
from pipeline import lexicon, rules, tagging
from pipeline.extract import PdfError, ScannedPdfError, extract_text


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


@app.after_request
def allow_local_frontend(resp):
    # Lets a frontend dev server on another localhost port call us during development.
    # Lock this down (or remove it) before anything is deployed.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.get("/health")
def health():
    return {"ok": True, "gliner": config.USE_GLINER, "lexicon": lexicon.load()}  # "tidb" | "csv" | "off"


@app.post("/analyze")
def analyze():
    # Accept either an uploaded file or raw text (handy for testing with curl).
    if "file" in request.files:
        f = request.files["file"]
        try:
            text = extract_text(f.filename, f.read())
        except ScannedPdfError as e:          # no text layer: say so, so the user can paste instead
            return jsonify(error=str(e)), 422
        except PdfError as e:                 # not a PDF, damaged, password protected, too many pages
            return jsonify(error=str(e)), 400
    else:
        text = (request.get_json(silent=True) or {}).get("text", "")
    if not text.strip():
        return jsonify(error="no text found (scanned PDFs aren't supported yet)"), 400
    if len(text) > config.MAX_TEXT_CHARS:
        return jsonify(error=f"document too long (max {config.MAX_TEXT_CHARS:,} characters)"), 413

    result = pipeline.analyze(text)
    log.info("analyze: %d chars | %s | risk=%s", len(text), pipeline.summary(result["spans"]), result["risk"])
    return jsonify(text=text, **result)


@app.post("/tag")
def tag():
    body = request.get_json()
    tagged, mapping = tagging.tag_text(body["text"], body["spans"], set(body["remove_ids"]))
    # The mapping is returned to the browser and NOT kept here.
    return jsonify(tagged_text=tagged, mapping=mapping)


@app.post("/chat")
def chat():
    body = request.get_json()
    note, history, question = body["tagged_note"], body.get("history", []), body["question"]

    # Last line of defence: refuse to send if a raw PHN/email slipped through.
    outgoing = "\n".join([note, question] + [h["text"] for h in history])
    problem = rules.looks_unsafe(outgoing)
    if problem:
        log.info("chat blocked: %s", problem)
        return jsonify(error=f"Blocked before sending: {problem}"), 400

    answer = gemini_client.ask(note, history, question)
    log.info("chat: sent %d chars to Gemini", len(outgoing))
    # We also return exactly what was sent, for the "AI received" view / outgoing-request log.
    return jsonify(answer=answer, sent={"note": note, "question": question, "history": history})


if __name__ == "__main__":
    # 127.0.0.1 = only this computer can reach it. Don't change to 0.0.0.0 unless you mean it.
    app.run(host="127.0.0.1", port=5000, debug=False)
