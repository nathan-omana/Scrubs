"""
Snowflake audit log (CLAUDE.md sections 9 and 10). Owned by Nathan; ported from nathan_branch
(backend/app/audit.py) into the Flask backend.

Writes decisions and counts to Snowflake. If Snowflake is not configured (SNOWFLAKE_ACCOUNT,
SNOWFLAKE_USER or SNOWFLAKE_PASSWORD unset) every call is a silent no-op, so the app runs
without credentials.

Schema (created on first write):
  audit_log(id, document_id, flag_code, label, tier, default_masked, final_masked, changed_by, changed_at)
  outbound_log(id, document_ids, word_count, identifier_count, model, sent_at)

PRIVACY RULE: no column ever holds original or pseudonymized text. These functions only accept
ids, codes, labels, tiers, booleans and counts, and they never raise.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

log = logging.getLogger("scrubin")


@lru_cache(maxsize=1)
def _conn() -> Any:
    """A Snowflake connection, or None if not configured or unreachable (tried once per process)."""
    account = os.getenv("SNOWFLAKE_ACCOUNT", "")
    user = os.getenv("SNOWFLAKE_USER", "")
    password = os.getenv("SNOWFLAKE_PASSWORD", "")
    if not (account and user and password):
        return None
    try:
        import snowflake.connector

        conn = snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
            database=os.getenv("SNOWFLAKE_DATABASE", "SCRUBS"),
            schema=os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE") or None,
            login_timeout=10,          # never hang a review click for long if Snowflake is down
            network_timeout=10,
        )
        _ensure_schema(conn)
        log.info("audit: Snowflake connected")
        return conn
    except Exception as e:
        log.info("audit: Snowflake unavailable (%s), audit log off", type(e).__name__)
        return None


def _ensure_schema(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id              VARCHAR(36) DEFAULT UUID_STRING(),
            document_id     VARCHAR(64),
            flag_code       VARCHAR(16),
            label           VARCHAR(64),
            tier            VARCHAR(8),
            default_masked  BOOLEAN,
            final_masked    BOOLEAN,
            changed_by      VARCHAR(128),
            changed_at      TIMESTAMP_TZ
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS outbound_log (
            id               VARCHAR(36) DEFAULT UUID_STRING(),
            document_ids     VARCHAR(1024),
            word_count       INTEGER,
            identifier_count INTEGER,
            model            VARCHAR(64),
            sent_at          TIMESTAMP_TZ
        )
    """)
    cur.close()


def log_flag_change(*, document_id: str, flag_code: str, label: str, tier: str,
                    default_masked: bool, final_masked: bool, changed_by: str) -> None:
    """One row per mask/unmask decision. No text."""
    try:
        conn = _conn()
        if conn is None:
            return
        conn.cursor().execute(
            """INSERT INTO audit_log
               (document_id, flag_code, label, tier, default_masked, final_masked, changed_by, changed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (document_id, flag_code, label, tier, bool(default_masked), bool(final_masked), changed_by,
             datetime.now(timezone.utc)),
        )
    except Exception as e:
        log.info("audit: flag change not logged (%s)", type(e).__name__)


def log_outbound(*, document_ids: list[str], word_count: int, identifier_count: int, model: str) -> None:
    """One row per message sent to Gemini. Counts only, no text."""
    try:
        conn = _conn()
        if conn is None:
            return
        conn.cursor().execute(
            """INSERT INTO outbound_log
               (document_ids, word_count, identifier_count, model, sent_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (",".join(document_ids), int(word_count), int(identifier_count), model, datetime.now(timezone.utc)),
        )
    except Exception as e:
        log.info("audit: outbound not logged (%s)", type(e).__name__)
