"""
Layer 3: the BC lexicon (a list of known identifying phrases), matched LOCALLY.

Where the list comes from:
  - TiDB Cloud table `bc_lexicon` (PUBLIC data only: BC towns, BC facilities, identifying occupations).
    Downloaded ONCE, read-only, the first time we need it. Data only ever comes DOWN from TiDB.
  - If TiDB isn't configured or can't be reached, we use data/lexicon_seed.csv from the repo.
    So the pipeline always works, even offline.

PRIVACY RULE: no note text is EVER sent to TiDB. We download the list and then do all
the matching here, in this process's memory.

Why a lexicon at all? GLiNER is good at context but scores some identifiers low
(e.g. "bush pilot" ~0.3). A curated list catches known risky phrases every time.
"""
import csv
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("scrubin")

SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "lexicon_seed.csv"

# "auto" = TiDB if TIDB_HOST is set, else CSV.  "csv" = always CSV.  "off" = no lexicon.
LEXICON_SOURCE = os.getenv("LEXICON_SOURCE", "auto").lower()

_entries: dict[str, dict] | None = None   # phrase -> {"type": ..., "ambiguous": bool}
_pattern: re.Pattern | None = None
source_used = None                         # "tidb" | "csv" | "off", handy for /health and the demo


def _load_from_tidb() -> list[dict]:
    """One read-only SELECT over TLS. Raises on any problem so the caller can fall back."""
    import certifi
    import pymysql

    conn = pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.getenv("TIDB_PORT", "4000")),
        user=os.environ["TIDB_USER"],          # should be the READ-ONLY 'gateway' user
        password=os.environ["TIDB_PASSWORD"],
        database=os.getenv("TIDB_DATABASE", "scrubin"),
        ssl_ca=certifi.where(),                # TiDB Cloud requires TLS
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        connect_timeout=5,
        read_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            # The ONLY query we ever send. It contains no note text.
            cur.execute("SELECT phrase, type, ambiguous FROM bc_lexicon")
            return [{"phrase": p, "type": t, "ambiguous": bool(a)} for p, t, a in cur.fetchall()]
    finally:
        conn.close()


def _load_from_csv() -> list[dict]:
    with open(SEED_CSV, newline="", encoding="utf-8") as f:
        return [{"phrase": r["phrase"], "type": r["type"], "ambiguous": r["ambiguous"] == "1"}
                for r in csv.DictReader(f)]


def load(force: bool = False) -> str:
    """Load the lexicon once (or again with force=True). Returns which source was used."""
    global _entries, _pattern, source_used
    if _entries is not None and not force:
        return source_used

    rows: list[dict] = []
    if LEXICON_SOURCE == "off":
        source_used = "off"
    elif LEXICON_SOURCE == "auto" and os.getenv("TIDB_HOST"):
        try:
            rows, source_used = _load_from_tidb(), "tidb"
        except Exception as e:                       # unreachable, bad password, etc.
            log.info("lexicon: TiDB unavailable (%s), using CSV fallback", type(e).__name__)
            rows, source_used = _load_from_csv(), "csv"
    else:
        rows, source_used = _load_from_csv(), "csv"

    _entries = {r["phrase"]: r for r in rows}
    # One big regex, LONGEST phrases first, so "Tofino General Hospital" wins over "Tofino".
    # Case-sensitive on purpose: "Hope" (town) vs "hope" (word).
    # (?<!\w) / (?!\w) = whole words only, so "Trail" won't match inside "Trailer".
    if _entries:
        alternatives = "|".join(re.escape(p) for p in sorted(_entries, key=len, reverse=True))
        _pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")
    else:
        _pattern = None
    log.info("lexicon: %d entries loaded from %s", len(_entries), source_used)   # counts only
    return source_used


def find(text: str) -> list[dict]:
    """Return lexicon matches in the same span format as rules.find() / detector.detect()."""
    load()
    if _pattern is None:
        return []
    spans = []
    for m in _pattern.finditer(text):
        entry = _entries[m.group()]
        spans.append({
            "start": m.start(),
            "end": m.end(),
            "type": entry["type"],
            "text": m.group(),
            "score": 1.0,                       # exact list match
            "source": "lexicon",
            # Ambiguous = also a common word or name (Hope, Golden, Nelson...).
            # merge.py only keeps these if GLiNER flagged the same place too.
            "ambiguous": entry["ambiguous"],
        })
    return spans
