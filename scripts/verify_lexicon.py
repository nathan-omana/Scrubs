"""
Prove the two things we tell the TiDB judges, using the gateway's own (read-only) login:

  1. The gateway CAN download the lexicon.
  2. The gateway CANNOT write anything to TiDB ("nothing goes up" is enforced by the database).

Run from the repo root:   python scripts/verify_lexicon.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main():
    import certifi
    import pymysql

    if not os.getenv("TIDB_HOST"):
        sys.exit("TIDB_HOST not set in .env (see TIDB_SETUP.md)")

    conn = pymysql.connect(
        host=os.environ["TIDB_HOST"], port=int(os.getenv("TIDB_PORT", "4000")),
        user=os.environ["TIDB_USER"], password=os.environ["TIDB_PASSWORD"],
        database=os.getenv("TIDB_DATABASE", "scrubin"),
        ssl_ca=certifi.where(), ssl_verify_cert=True, ssl_verify_identity=True,
    )
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM bc_lexicon")
        print(f"1. READ  ok: gateway user can see {cur.fetchone()[0]} lexicon rows")

        try:
            # A harmless test write. It SHOULD fail.
            cur.execute("INSERT INTO bc_lexicon (phrase, type) VALUES ('__write_test__', 'LOCATION')")
            conn.rollback()
            print("2. WRITE ALLOWED: the gateway user can write. Fix its grants (SELECT only)!")
            sys.exit(1)
        except pymysql.err.MySQLError as e:          # TiDB answers "INSERT command denied"
            print(f"2. WRITE blocked as expected: {str(e)[:100]}")
    conn.close()

    # And the real loader, exactly as the server uses it:
    sys.path.insert(0, str(ROOT / "backend"))
    from pipeline import lexicon
    print(f"3. lexicon.load() used source: {lexicon.load(force=True)}")


if __name__ == "__main__":
    main()
