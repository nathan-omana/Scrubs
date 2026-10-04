"""
Tagging (real value -> [TYPE_n]) and restoring (tags in Gemini's answer -> real values).
Run from the backend folder:   python -m tests.test_tagging
"""
from pipeline import tagging
from tests._util import run


def spans_for(text, items):
    """items = [(value, type)], first occurrence of each. Returns spans with ids."""
    out = []
    for i, (value, type_) in enumerate(items):
        start = text.index(value)
        out.append({"id": i, "start": start, "end": start + len(value), "type": type_})
    return out


def tag_all(text, items):
    spans = spans_for(text, items)
    return tagging.tag_text(text, spans, {s["id"] for s in spans})


# ---------- tagging ----------

def test_tags_in_reading_order_and_mapping_round_trips():
    text = "Jane Doe called Bob Ray. Jane Doe is fine."
    tagged, mapping = tag_all(text, [("Bob Ray", "PERSON"), ("Jane Doe", "PERSON")])
    assert tagged == "[PERSON_1] called [PERSON_2]. [PERSON_1] is fine."
    assert mapping == {"[PERSON_1]": "Jane Doe", "[PERSON_2]": "Bob Ray"}
    assert tagging.restore(tagged, mapping) == text


def test_same_value_any_case_gets_same_tag():
    text = "Seen in Tofino. TOFINO clinic. tofino ferry."
    tagged, mapping = tag_all(text, [("Tofino", "LOCATION")])
    assert tagged == "Seen in [LOCATION_1]. [LOCATION_1] clinic. [LOCATION_1] ferry."
    assert "tofino" not in tagged.lower()


def test_repeats_are_whole_words_only():
    text = "Lives in Hope. Hopeful about rehab."
    tagged, _ = tag_all(text, [("Hope", "LOCATION")])
    assert tagged == "Lives in [LOCATION_1]. Hopeful about rehab."


def test_only_chosen_ids_are_tagged():
    text = "Jane Doe takes apixaban."
    spans = spans_for(text, [("Jane Doe", "PERSON"), ("apixaban", "DRUG")])
    tagged, mapping = tagging.tag_text(text, spans, {0})
    assert tagged == "[PERSON_1] takes apixaban."
    assert list(mapping) == ["[PERSON_1]"]


def test_nothing_chosen_changes_nothing():
    text = "Jane Doe takes apixaban."
    spans = spans_for(text, [("Jane Doe", "PERSON")])
    assert tagging.tag_text(text, spans, set()) == (text, {})


def test_repeat_of_value_starting_with_punctuation_is_tagged():
    # A phone written "(250) 555-0142" twice: the second copy must not leak.
    text = "Call (250) 555-0142. If no answer, (250) 555-0142 again."
    tagged, _ = tag_all(text, [("(250) 555-0142", "PHONE")])
    assert "555-0142" not in tagged, tagged


def test_unicode_names():
    text = "Zoë Côté-Nguyen, seen by Dr. Siobhán Ó Briain."
    tagged, mapping = tag_all(text, [("Zoë Côté-Nguyen", "PERSON"), ("Siobhán Ó Briain", "PERSON")])
    assert tagged == "[PERSON_1], seen by Dr. [PERSON_2]."
    assert tagging.restore(tagged, mapping) == text


def test_no_masked_value_survives_on_sample_note():
    text = open("sample_note.txt").read()
    items = [("Margaret Ellison", "PERSON"), ("9123 947 241", "PHN"), ("03/14/1951", "DATE"),
             ("211 Campbell St", "ADDRESS"), ("Tofino", "LOCATION"), ("V0R 2Z0", "POSTAL"),
             ("(250) 555-0142", "PHONE"), ("Claire", "PERSON"), ("claire.ellison@example.com", "EMAIL"),
             ("Raj Patel", "PERSON")]
    tagged, mapping = tag_all(text, items)
    for value, _ in items:
        assert value.lower() not in tagged.lower(), f"leaked: {value}"
    assert "Parkinson's" in tagged and "nitrofurantoin 100 mg BID" in tagged
    assert tagging.restore(tagged, mapping) == text


# ---------- restoring ----------

def test_restore_handles_altered_tags():
    m = {"[PERSON_1]": "Jane Doe"}
    for variant in ["[PERSON_1]", "PERSON_1", "[Person 1]", "[ PERSON_1 ]", "person_1"]:
        assert tagging.restore(f"Dear {variant},", m) == "Dear Jane Doe,", variant


def test_restore_leaves_unknown_and_invented_tags():
    m = {"[PERSON_1]": "Jane Doe"}
    assert tagging.restore("[PERSON_3] and [PHN_9]", m) == "[PERSON_3] and [PHN_9]"


def test_restore_leaves_ordinary_text_alone():
    m = {"[PERSON_1]": "Jane Doe", "[DATE_2]": "2026-09-02"}
    text = "Type 2 diabetes, COVID 19 vaccine, Day 5, step 1, ICD 10, Apixaban 5 mg."
    assert tagging.restore(text, m) == text


def test_restore_does_not_confuse_1_and_10():
    m = {f"[PERSON_{i}]": f"Name{i}" for i in range(1, 12)}
    assert tagging.restore("[PERSON_10] [PERSON_1] [PERSON_11]", m) == "Name10 Name1 Name11"


def test_restore_never_crashes_on_junk():
    m = {"[PERSON_1]": "Jane Doe"}
    for junk in ["", "[", "]", "[[PERSON_1]]", "[PERSON_]", "[_1]", "\x00", "[PERSON_99999999999999999999]"]:
        tagging.restore(junk, m)


# ---------- tagging the clinician's question ----------

def test_question_names_are_tagged_any_case():
    m = {"[PERSON_1]": "Jane Doe", "[PERSON_2]": "Jane"}
    assert tagging.tag_question("How is JANE DOE doing?", m) == "How is [PERSON_1] doing?"


def test_question_tagging_is_whole_words_only():
    # A short masked value ("74", an age) must not eat parts of other numbers or words.
    m = {"[AGE_1]": "74", "[LOCATION_1]": "Hope"}
    q = "Give 740 mg? Hopeful plan for the 74 year old in Hope."
    assert tagging.tag_question(q, m) == "Give 740 mg? Hopeful plan for the [AGE_1] year old in [LOCATION_1]."


if __name__ == "__main__":
    run(globals())
