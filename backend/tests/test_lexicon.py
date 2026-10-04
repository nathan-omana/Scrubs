"""
Lexicon checks. No TiDB account or GLiNER download needed (both are faked).
Run from the backend folder:   python -m tests.test_lexicon
"""
import os
import sys
import types

import config
from pipeline import detector, lexicon, merge


class NoGLiNER:
    """A GLiNER that finds nothing, to prove the lexicon works on its own."""
    def predict_entities(self, text, labels, threshold=0.5):
        return []


def fresh(source="csv"):
    lexicon.LEXICON_SOURCE = source
    lexicon._entries = None
    return lexicon.load()


def test_csv_fallback_loads():
    assert fresh("csv") == "csv"
    assert len(lexicon._entries) > 300
    assert lexicon._entries["Tofino"]["ambiguous"] is False
    assert lexicon._entries["Hope"]["ambiguous"] is True


def test_catches_occupation_gliner_missed():
    fresh("csv")
    config.USE_GLINER = True
    detector._model = NoGLiNER()
    import pipeline
    r = pipeline.analyze("Pt is a retired bush pilot who lives alone in Tofino.")
    found = {s["text"]: s for s in r["spans"]}
    assert found["bush pilot"]["type"] == "OCCUPATION" and found["bush pilot"]["found_by"] == ["lexicon"]
    assert found["Tofino"]["type"] == "LOCATION"


def test_ambiguous_needs_gliner():
    fresh("csv")
    text = "Hope she improves. Moved to Hope last year."
    lex = lexicon.find(text)
    assert [s["text"] for s in lex] == ["Hope", "Hope"]               # both matched by the list...
    assert merge.merge(text, [], [], lex) == []                         # ...but dropped without GLiNER
    gliner_town = [{"start": 28, "end": 32, "type": "LOCATION", "score": 0.8, "source": "gliner"}]
    out = merge.merge(text, [], gliner_town, lex)
    assert len(out) == 1 and out[0]["start"] == 28 and out[0]["found_by"] == ["gliner", "lexicon"]
    assert "ambiguous" not in out[0]                                    # internal flag not exposed


def test_case_and_whole_words():
    fresh("csv")
    assert lexicon.find("I hope the trail is clear") == []              # lowercase words, not towns
    assert lexicon.find("Trailer park") == []                           # no partial-word matches
    hits = lexicon.find("Admitted to Tofino General Hospital")
    assert [(h["text"], h["type"]) for h in hits] == [("Tofino General Hospital", "FACILITY")]  # longest wins


def test_priority_gliner_over_lexicon():
    text = "retired bush pilot"
    g = [{"start": 0, "end": 18, "type": "OCCUPATION", "score": 0.5, "source": "gliner"}]
    l = [{"start": 8, "end": 18, "type": "LOCATION", "score": 1.0, "source": "lexicon", "ambiguous": False}]
    out = merge.merge(text, [], g, l)
    assert out[0]["type"] == "OCCUPATION" and out[0]["found_by"] == ["gliner", "lexicon"]


def test_tidb_path_with_fake_database():
    """Exercise the real TiDB code path against a fake pymysql (no network)."""
    sent_sql = []

    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql): sent_sql.append(sql)
        def fetchall(self): return [("Tofino", "LOCATION", 0), ("bush pilot", "OCCUPATION", 0)]

    class Conn:
        def cursor(self): return Cur()
        def close(self): pass

    fake = types.SimpleNamespace(connect=lambda **kw: Conn())
    sys.modules["pymysql"] = fake
    os.environ.update(TIDB_HOST="fake.tidbcloud.com", TIDB_USER="x.gateway", TIDB_PASSWORD="pw")
    try:
        assert fresh("auto") == "tidb"
        assert sent_sql == ["SELECT phrase, type, ambiguous FROM bc_lexicon"]   # the ONLY query, no note text
        assert len(lexicon.find("bush pilot from Tofino")) == 2
        # Unreachable database -> CSV fallback, pipeline keeps working
        fake.connect = lambda **kw: (_ for _ in ()).throw(ConnectionError("down"))
        assert fresh("auto") == "csv"
    finally:
        del sys.modules["pymysql"]
        for k in ("TIDB_HOST", "TIDB_USER", "TIDB_PASSWORD"):
            os.environ.pop(k, None)


if __name__ == "__main__":
    test_csv_fallback_loads()
    test_catches_occupation_gliner_missed()
    test_ambiguous_needs_gliner()
    test_case_and_whole_words()
    test_priority_gliner_over_lexicon()
    test_tidb_path_with_fake_database()
    print("all lexicon tests passed")
