"""
Create the `bc_lexicon` table in TiDB Cloud and load data/lexicon_seed.csv into it.

Run MANUALLY by the team (never by the server), from the repo root:
    python scripts/seed_lexicon.py            # create table if needed + upsert all rows
    python scripts/seed_lexicon.py --dry-run  # just show what would be loaded

Uses the ADMIN credentials (TIDB_ADMIN_USER / TIDB_ADMIN_PASSWORD), because it writes.
The gateway itself uses a separate READ-ONLY user (see TIDB_SETUP.md).

Only PUBLIC data goes in here: BC town names, BC facilities, occupation titles.
NEVER put note text, patient names, or tag mappings in TiDB.
"""
import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
CSV_PATH = ROOT / "data" / "lexicon_seed.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bc_lexicon (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  phrase     VARCHAR(120) NOT NULL,
  type       VARCHAR(20)  NOT NULL,          -- LOCATION | FACILITY | OCCUPATION
  ambiguous  BOOLEAN      NOT NULL DEFAULT FALSE,  -- also a common word/name -> only counts if GLiNER agrees
  version    INT          NOT NULL DEFAULT 1,
  updated_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_phrase_type (phrase, type)
)
"""


def read_csv() -> list[tuple]:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = [(r["phrase"].strip(), r["type"].strip(), r["ambiguous"].strip() == "1")
                for r in csv.DictReader(f)]
    # Basic sanity checks, so bad rows never reach the database.
    bad = [r for r in rows if not r[0] or r[1] not in {"LOCATION", "FACILITY", "OCCUPATION"}]
    if bad:
        sys.exit(f"Bad rows in CSV (empty phrase or unknown type): {bad[:5]}")
    return rows


def connect():
    import certifi
    import pymysql
    missing = [v for v in ("TIDB_HOST", "TIDB_ADMIN_USER", "TIDB_ADMIN_PASSWORD") if not os.getenv(v)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)} (see TIDB_SETUP.md)")
    return pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.getenv("TIDB_PORT", "4000")),
        user=os.environ["TIDB_ADMIN_USER"],
        password=os.environ["TIDB_ADMIN_PASSWORD"],
        database=os.getenv("TIDB_DATABASE", "scrubin"),
        ssl_ca=certifi.where(), ssl_verify_cert=True, ssl_verify_identity=True,
        autocommit=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = read_csv()
    print(f"CSV: {len(rows)} rows  {dict(Counter(r[1] for r in rows))}  ambiguous={sum(r[2] for r in rows)}")
    if args.dry_run:
        return

    conn = connect()
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        # Upsert: new phrases are added; existing ones get their ambiguous flag updated and version bumped.
        cur.executemany(
            "INSERT INTO bc_lexicon (phrase, type, ambiguous) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE ambiguous = VALUES(ambiguous), version = version + 1",
            rows,
        )
        cur.execute("SELECT type, COUNT(*) FROM bc_lexicon GROUP BY type ORDER BY type")
        print("TiDB now has:", dict(cur.fetchall()))
    conn.close()


if __name__ == "__main__":
    main()
