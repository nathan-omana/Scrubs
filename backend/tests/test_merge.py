"""
Merging findings from the three layers.
Run from the backend folder:   python -m tests.test_merge
"""
from pipeline import merge
from tests._util import run


def span(start, end, type_, source, score=0.9, **extra):
    return {"start": start, "end": end, "type": type_, "score": score, "source": source, **extra}


def check_invariants(text, out):
    """Every merged list must be sorted, non-overlapping, numbered 0..n-1, with matching text."""
    for i, s in enumerate(out):
        assert s["id"] == i
        assert s["text"] == text[s["start"]:s["end"]]
        assert s["start"] < s["end"]
        assert "ambiguous" not in s
        if i:
            assert out[i - 1]["end"] <= s["start"], "overlapping spans after merge"


def test_empty():
    assert merge.merge("anything", [], [], []) == []


def test_overlapping_spans_join_into_one():
    text = "Pt Margaret Ellison here"
    out = merge.merge(text, [span(3, 11, "PERSON", "rules")], [span(3, 19, "PERSON", "gliner")])
    check_invariants(text, out)
    assert len(out) == 1 and out[0]["text"] == "Margaret Ellison"
    # spaCy's "Margaret" sits fully inside GLiNER's span, so GLiNER's precise span replaces it.
    assert out[0]["found_by"] == ["gliner"]


def test_touching_spans_stay_separate():
    text = "Tofino,Ucluelet"
    out = merge.merge(text, [], [span(0, 7, "LOCATION", "gliner"), span(7, 15, "LOCATION", "gliner")])
    check_invariants(text, out)
    assert len(out) == 2


def test_partial_overlap_grows_to_cover_both():
    text = "abcdefghij"
    out = merge.merge(text, [span(0, 5, "DATE", "rules")], [span(3, 8, "AGE", "gliner")])
    check_invariants(text, out)
    assert (out[0]["start"], out[0]["end"]) == (0, 8)
    assert out[0]["found_by"] == ["gliner", "rules"] and out[0]["type"] == "DATE"


def test_chain_of_overlaps_becomes_one_span():
    text = "a" * 30
    out = merge.merge(text, [], [span(0, 10, "ORG", "gliner"), span(8, 20, "ORG", "gliner"),
                                 span(18, 30, "ORG", "gliner")])
    check_invariants(text, out)
    assert len(out) == 1 and (out[0]["start"], out[0]["end"]) == (0, 30)


def test_type_priority_structured_beats_model_beats_lexicon_beats_spacy():
    text = "x" * 20
    rule = span(0, 10, "PHN", "rules", 0.5)
    model = span(0, 10, "AGE", "gliner", 0.99)
    lex = span(0, 10, "LOCATION", "lexicon", 1.0)
    spacy = span(0, 10, "PERSON", "rules", 1.0)
    assert merge.merge(text, [rule], [model], [lex])[0]["type"] == "PHN"
    # spaCy's PERSON fully covered by a GLiNER span that isn't about a person: GLiNER's reading stands.
    assert merge.merge(text, [spacy], [model], [lex])[0]["type"] == "AGE"
    # Same tier: detector priority decides (GLiNER > lexicon).
    assert merge.merge(text, [], [model], [lex])[0]["type"] == "AGE"
    # A HIGH type beats a MED one regardless of source.
    assert merge.merge(text, [], [span(0, 10, "PERSON", "gliner", 0.3)], [lex])[0]["type"] == "PERSON"


def test_clinical_label_never_unmasks_an_identifier():
    # Real case: GLiNER called "MRN 4482913" a Drug (LOW, kept), so the MRN went to Gemini.
    text = "Pt seen, MRN 4482913, stable."
    a, b = text.index("4482913"), text.index("MRN")
    rule = span(a, a + 7, "MRN", "rules", 0.9)
    model = span(b, a + 7, "DRUG", "gliner", 0.56)
    out = merge.merge(text, [rule], [model])
    assert len(out) == 1 and out[0]["type"] == "MRN" and out[0]["text"] == "MRN 4482913"


def test_name_stays_high_when_gliner_calls_it_a_relative():
    # Real case: GLiNER labelled the patient "Mrs. Eleanor Park" as a family member (MED, unlockable).
    text = "Mrs. Eleanor Park, 72, was admitted."
    out = merge.merge(text, [span(5, 17, "PERSON", "rules", 0.85)], [span(0, 17, "RELATION", "gliner", 0.87)])
    assert len(out) == 1 and out[0]["type"] == "PERSON" and out[0]["text"] == "Mrs. Eleanor Park"


def test_priority_holds_regardless_of_order_or_length():
    # The shorter structured span starts later but must still decide the type.
    text = "PHN 9123 947 241 ok"
    out = merge.merge(text, [span(4, 16, "PHN", "rules", 0.5)], [span(0, 16, "PERSON", "gliner", 0.95)])
    assert out[0]["type"] == "PHN"


def test_never_redact_eponyms():
    text = "Hx of Parkinson's, Foley in situ, BELL'S palsy, Crohn's flare."
    rule_spans = [span(text.index(w), text.index(w) + len(w), "PERSON", "rules")
                  for w in ["Parkinson's", "Foley", "BELL'S", "Crohn's"]]
    assert merge.merge(text, rule_spans, []) == []


def test_never_redact_with_curly_apostrophe():
    # Word processors and PDFs write Bell’s with a curly apostrophe (U+2019).
    text = "New Bell’s palsy, Parkinson’s stable."
    rule_spans = [span(4, 10, "PERSON", "rules"), span(18, 29, "PERSON", "rules")]
    assert [text[s["start"]:s["end"]] for s in rule_spans] == ["Bell’s", "Parkinson’s"]
    assert merge.merge(text, rule_spans, []) == []


def test_never_redact_only_applies_to_single_words():
    # A real person called Dr. Foley is still a name.
    text = "Seen by Dr. Foley today"
    out = merge.merge(text, [span(8, 17, "PERSON", "rules")], [])
    assert len(out) == 1 and out[0]["text"] == "Dr. Foley"


def test_chart_words_never_redacted():
    text = "Pt seen. DOB unknown. Hx BC."
    spans = [span(0, 2, "PERSON", "gliner"), span(9, 12, "DATE", "gliner"),
             span(22, 24, "PERSON", "gliner"), span(25, 27, "LOCATION", "gliner")]
    assert merge.merge(text, [], spans) == []


def test_spacy_person_dropped_only_when_fully_covered():
    text = "Daughter Claire visits"
    spacy = span(0, 15, "PERSON", "rules")
    covered = merge.merge(text, [spacy], [span(0, 8, "RELATION", "gliner"), span(9, 15, "PERSON", "gliner")])
    check_invariants(text, covered)
    # Fully covered: spaCy's blurry span must not survive as its own PERSON finding.
    assert all(s["found_by"] != ["rules"] for s in covered)
    # Partly covered: spaCy's span is kept, so "Claire" is never left unflagged.
    partial = merge.merge(text, [spacy], [span(0, 8, "RELATION", "gliner")])
    assert any(s["start"] <= 9 and s["end"] >= 15 for s in partial)


def test_ambiguous_lexicon_needs_gliner():
    text = "Hope she improves. Moved to Hope."
    lex = [span(0, 4, "LOCATION", "lexicon", 1.0, ambiguous=True),
           span(28, 32, "LOCATION", "lexicon", 1.0, ambiguous=True)]
    assert merge.merge(text, [], [], lex) == []
    out = merge.merge(text, [], [span(28, 32, "LOCATION", "gliner")], lex)
    check_invariants(text, out)
    assert [s["start"] for s in out] == [28]


def test_ambiguous_lexicon_not_rescued_by_spacy():
    # Only GLiNER (context-aware) can confirm an ambiguous hit, not spaCy's PERSON guess.
    text = "Nelson called."
    out = merge.merge(text, [span(0, 6, "PERSON", "rules")], [],
                      [span(0, 6, "LOCATION", "lexicon", 1.0, ambiguous=True)])
    assert len(out) == 1 and out[0]["found_by"] == ["rules"]


def test_inputs_are_not_mutated():
    text = "Tofino"
    g = [span(0, 6, "LOCATION", "gliner")]
    before = [dict(s) for s in g]
    merge.merge(text, [], g)
    assert g == before


if __name__ == "__main__":
    run(globals())
