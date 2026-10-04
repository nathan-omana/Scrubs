"""
The hard rules (CLAUDE.md section 14), checked directly:
  - no network calls during detection
  - nothing written to disk
  - logs hold counts only
  - nothing raw reaches Gemini
  - only the allowed files can talk to the internet
GLiNER and Gemini are faked. Run from the backend folder:   python -m tests.test_privacy
"""
import io
import logging
import re
import socket
import sys
from pathlib import Path

import config
import gemini_client
from pipeline import lexicon, rules, tagging
from tests._util import run, use_fake_gliner
from tests.pdf_factory import build_pdf

BACKEND = Path(__file__).resolve().parents[1]
NOTE = (BACKEND / "sample_note.txt").read_text()

# Values that must never appear in logs, on disk or in a Gemini request.
SECRETS = ["Margaret", "Ellison", "9123 947 241", "9123947241", "03/14/1951", "Campbell",
           "V0R 2Z0", "555-0142", "claire.ellison", "Raj Patel", "Tofino", "bush pilot"]

GLINER_PHRASES = {"Margaret Ellison": "person name", "bush pilot": "occupation", "Tofino": "city or town",
                  "74-year-old": "age", "Claire": "family member", "211 Campbell St": "street address",
                  "Dr. Raj Patel": "doctor"}


# ---------- watchers ----------

_writes: list[str] = []
_serving = False     # True only while the SERVER handles a request (the test client itself
                     # spools big fake uploads to a temp file, which is not the server's doing)


def _audit(event, args):
    # Python's audit hooks see every file open. Record any open for writing.
    if event == "open" and _serving and len(args) >= 2:
        path, mode = args[0], args[1]
        if "__pycache__" in str(path):                  # Python's own bytecode cache, not our data
            return
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            _writes.append(str(path))
        elif isinstance(mode, int) and mode & 0o3:      # os.open flags: O_WRONLY / O_RDWR
            _writes.append(str(path))


sys.addaudithook(_audit)


class NoNetwork:
    """Any attempt to open a network connection inside this block raises and is recorded."""

    def __init__(self):
        self.attempts: list[str] = []

    def __enter__(self):
        self._connect, self._create = socket.socket.connect, socket.create_connection
        attempts = self.attempts

        def blocked(*args, **kwargs):
            attempts.append(repr(args[1:] if args else kwargs)[:80])
            raise OSError("network blocked by test")

        socket.socket.connect = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, *exc):
        socket.socket.connect, socket.create_connection = self._connect, self._create


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())

    def __enter__(self):
        logging.getLogger().addHandler(self)
        return self

    def __exit__(self, *exc):
        logging.getLogger().removeHandler(self)


class FakeGenai:
    """Stands in for google.genai's client and records exactly what would be sent."""

    def __init__(self):
        self.requests: list[str] = []
        self.models = self

    def generate_content(self, model, contents, config):
        parts = [config.system_instruction] + [p.text for c in contents for p in c.parts]
        self.requests.append("\n".join(parts))
        return type("R", (), {"text": "Referral for [PERSON_1] regarding [LOCATION_1]."})()


def client():
    use_fake_gliner(GLINER_PHRASES)
    import app as app_module
    if not getattr(app_module.app, "_watched", False):
        def start(*_):
            global _serving
            _serving = True

        def stop(*_):
            global _serving
            _serving = False

        app_module.app.before_request(start)
        app_module.app.teardown_request(stop)
        app_module.app._watched = True
    return app_module.app.test_client()


def full_flow(c):
    """Upload -> tag everything -> chat. Returns the /chat response."""
    r = c.post("/analyze", data={"file": (io.BytesIO(NOTE.encode()), "note.txt")},
               content_type="multipart/form-data")
    assert r.status_code == 200, r.json
    spans = r.json["spans"]
    t = c.post("/tag", json={"text": r.json["text"], "spans": spans, "remove_ids": [s["id"] for s in spans]})
    question = tagging.tag_question("Draft a referral for Margaret Ellison", t.json["mapping"])
    return c.post("/chat", json={"tagged_note": t.json["tagged_text"], "history": [], "question": question})


# ---------- tests ----------

def test_detection_makes_no_network_calls():
    lexicon.LEXICON_SOURCE, lexicon._entries = "auto", None     # auto + no TIDB_HOST -> CSV
    c = client()
    with NoNetwork() as net:
        r = c.post("/analyze", json={"text": NOTE})
        assert r.status_code == 200
        c.post("/analyze", data={"file": (io.BytesIO(build_pdf([[NOTE]])), "n.pdf")},
               content_type="multipart/form-data")
    assert net.attempts == [], net.attempts


def test_nothing_written_to_disk():
    c = client()
    gemini_client._client = FakeGenai()
    _writes.clear()
    c.post("/analyze", data={"file": (io.BytesIO(build_pdf([[NOTE]] * 5)), "n.pdf")},
           content_type="multipart/form-data")
    big_txt = NOTE.encode() + b"\n" + b"x" * 600_000                          # Werkzeug spills > 500 KB to disk by default
    config.MAX_TEXT_CHARS = 700_000
    try:
        c.post("/analyze", data={"file": (io.BytesIO(big_txt), "n.txt")}, content_type="multipart/form-data")
    finally:
        config.MAX_TEXT_CHARS = 200_000
    full_flow(c)
    assert _writes == [], _writes


def test_logs_hold_counts_only():
    c = client()
    gemini_client._client = FakeGenai()
    with LogCapture() as logs:
        full_flow(c)
        c.post("/chat", json={"tagged_note": "PHN 9123947241", "history": [], "question": "hi"})
    assert logs.lines, "expected some log lines"
    joined = "\n".join(logs.lines)
    for s in SECRETS:
        assert s.lower() not in joined.lower(), f"log leaked {s!r}"
    # No run of 4+ words from the note in any log line.
    words = re.findall(r"[A-Za-z']+", NOTE)
    for i in range(len(words) - 3):
        phrase = " ".join(words[i:i + 4])
        assert phrase not in joined, f"log contains note text: {phrase!r}"


def test_gemini_never_receives_masked_values():
    c = client()
    fake = FakeGenai()
    gemini_client._client = fake
    r = full_flow(c)
    assert r.status_code == 200, r.json
    assert len(fake.requests) == 1
    sent = fake.requests[0]
    for s in SECRETS:
        assert s.lower() not in sent.lower(), f"Gemini request contained {s!r}"
    assert "Parkinson's" in sent and "nitrofurantoin" in sent        # clinical content is kept


def test_chat_blocks_raw_identifiers_anywhere_in_the_request():
    c = client()
    fake = FakeGenai()
    gemini_client._client = fake
    cases = [
        {"tagged_note": "PHN 9123 947 241", "history": [], "question": "hi"},
        {"tagged_note": "ok", "history": [], "question": "email jo.doe@example.com"},
        {"tagged_note": "ok", "history": [{"role": "user", "text": "PHN 9123947241"}], "question": "hi"},
        {"tagged_note": "ok", "history": [{"role": "model", "text": "jo.doe@example.com"}], "question": "hi"},
    ]
    for body in cases:
        r = c.post("/chat", json=body)
        assert r.status_code == 400, body
    assert fake.requests == [], "a blocked request still reached Gemini"


def test_only_allowed_files_import_network_libraries():
    allowed = {"gemini_client.py", "audit.py", "pipeline/lexicon.py"}
    net = re.compile(r"^\s*(import|from)\s+(requests|urllib|http|socket|httpx|aiohttp|google|pymysql|"
                     r"snowflake|websocket|ftplib|smtplib)\b", re.M)
    offenders = []
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith("tests/") or rel in allowed:
            continue
        if net.search(path.read_text()):
            offenders.append(rel)
    assert offenders == [], offenders


def test_presidio_logs_errors_only():
    assert logging.getLogger("presidio-analyzer").level >= logging.ERROR


def test_server_binds_to_localhost():
    src = (BACKEND / "app.py").read_text()
    assert 'host="127.0.0.1"' in src and "0.0.0.0" not in src.split("app.run")[-1]


def test_cors_allows_the_frontend_origin_only():
    c = client()
    r = c.get("/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("Access-Control-Allow-Origin") in (None, "http://localhost:3000"), \
        r.headers.get("Access-Control-Allow-Origin")


def test_uploads_over_the_size_limit_are_refused():
    c = client()
    too_big = b"x" * (config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    r = c.post("/analyze", data={"file": (io.BytesIO(too_big), "n.txt")}, content_type="multipart/form-data")
    assert r.status_code == 413


if __name__ == "__main__":
    run(globals())
