"""
backend/audit.py (Snowflake). Snowflake is faked; nothing leaves the machine.
Run from the backend folder:   python -m tests.test_audit
"""
import inspect
import os
import sys
import types

import audit
from tests._util import run
from tests.test_privacy import NoNetwork

ENV = {"SNOWFLAKE_ACCOUNT": "acct", "SNOWFLAKE_USER": "u", "SNOWFLAKE_PASSWORD": "pw"}


class FakeSnowflake:
    """Stands in for snowflake.connector and records every statement and its parameters."""

    def __init__(self, fail_on_insert=False):
        self.statements: list[tuple[str, tuple]] = []
        self.fail_on_insert = fail_on_insert
        self.connect_kwargs = None
        fake = self

        class Cursor:
            def execute(self, sql, params=()):
                if fake.fail_on_insert and "INSERT" in sql:
                    raise RuntimeError("warehouse suspended")
                fake.statements.append((sql, params))

            def close(self):
                pass

        class Conn:
            def cursor(self):
                return Cursor()

        def connect(**kw):
            fake.connect_kwargs = kw
            return Conn()

        self.module = types.SimpleNamespace(connect=connect)

    def __enter__(self):
        sys.modules["snowflake"] = types.SimpleNamespace(connector=self.module)
        sys.modules["snowflake.connector"] = self.module
        os.environ.update(ENV)
        audit._conn.cache_clear()
        return self

    def __exit__(self, *exc):
        for k in ("snowflake", "snowflake.connector"):
            sys.modules.pop(k, None)
        for k in ENV:
            os.environ.pop(k, None)
        audit._conn.cache_clear()

    def inserts(self):
        return [(sql, p) for sql, p in self.statements if "INSERT" in sql]


FLAG_CHANGE = dict(document_id="doc-abc", flag_code="F5", label="Unique role", tier="med",
                   default_masked=True, final_masked=False, changed_by="Dr. A. Singh")
OUTBOUND = dict(document_ids=["doc-abc", "doc-def"], word_count=120, identifier_count=0, model="gemini-2.5-flash")


def test_signatures_match_what_app_calls():
    # app.py calls these with keyword arguments; a renamed parameter would silently drop audit rows.
    assert list(inspect.signature(audit.log_flag_change).parameters) == list(FLAG_CHANGE)
    assert list(inspect.signature(audit.log_outbound).parameters) == list(OUTBOUND)


def test_noop_without_credentials_and_no_network():
    for k in ENV:
        os.environ.pop(k, None)
    audit._conn.cache_clear()
    with NoNetwork() as net:
        assert audit.log_flag_change(**FLAG_CHANGE) is None
        assert audit.log_outbound(**OUTBOUND) is None
    assert net.attempts == []


def test_writes_one_row_each_with_no_text():
    with FakeSnowflake() as sf:
        audit.log_flag_change(**FLAG_CHANGE)
        audit.log_outbound(**OUTBOUND)
        rows = sf.inserts()
    assert len(rows) == 2
    (sql1, p1), (sql2, p2) = rows
    assert "audit_log" in sql1 and p1[:7] == ("doc-abc", "F5", "Unique role", "med", True, False, "Dr. A. Singh")
    assert "outbound_log" in sql2 and p2[:4] == ("doc-abc,doc-def", 120, 0, "gemini-2.5-flash")


def test_tables_have_no_text_columns():
    with FakeSnowflake() as sf:
        audit.log_outbound(**OUTBOUND)
        ddl = " ".join(sql for sql, _ in sf.statements if "CREATE" in sql).lower()
    for banned in ["sent_text", "original", "pseudonymized", "note", "message", "answer"]:
        assert banned not in ddl, banned


def test_never_raises():
    with FakeSnowflake(fail_on_insert=True):
        audit.log_flag_change(**FLAG_CHANGE)
        audit.log_outbound(**OUTBOUND)

    def broken_connect(**kw):
        raise ConnectionError("no network")

    with FakeSnowflake() as sf:
        sf.module.connect = broken_connect
        audit._conn.cache_clear()
        audit.log_flag_change(**FLAG_CHANGE)


def test_connection_has_timeouts():
    with FakeSnowflake() as sf:
        audit.log_outbound(**OUTBOUND)
        kw = sf.connect_kwargs
    assert kw["login_timeout"] <= 15 and kw["network_timeout"] <= 15


if __name__ == "__main__":
    run(globals())
