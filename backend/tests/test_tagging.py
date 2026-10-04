"""
Pseudonyms (real value -> [PATIENT_01]), pseudonymizing, and restoring Gemini's answer.
Run from the backend folder:   python -m tests.test_tagging
"""
from pipeline import tagging
from tests._util import run


def flags_for(text, items, masked=True):
    """items = [(value, prefix)], first occurrence of each. Returns flags with pseudonyms."""
    p = tagging.Pseudonyms()
    out = []
    for value, prefix in items:
        start = text.index(value)
        out.append({"start_idx": start, "end_idx": start + len(value), "text": value,
                    "masked": masked, "pseudonym": p.get(prefix, value)})
    return out


# ---------- pseudonyms ----------

def test_format_is_prefix_and_two_digits():
    p = tagging.Pseudonyms()
    assert [p.get("PATIENT", n) for n in ["Jane Doe", "Bob Ray"]] == ["[PATIENT_01]", "[PATIENT_02]"]
    assert p.get("HCN", "9123 947 241") == "[HCN_01]"           # numbering is per prefix


def test_same_value_same_pseudonym_after_normalizing():
    p = tagging.Pseudonyms()
    a = p.get("PATIENT", "Mrs. Eleanor Park")
    assert p.get("PATIENT", "eleanor  park") == a
    assert p.get("PATIENT", " ELEANOR PARK ") == a
    assert p.get("PROVIDER", "Dr. Amrit Singh") == p.get("PROVIDER", "Amrit Singh")


def test_different_prefix_never_shares():
    p = tagging.Pseudonyms()
    assert p.get("LOC", "Hope") != p.get("ROLE", "Hope")


def test_normalize_strips_titles_only_at_the_start():
    assert tagging.normalize("Dr. Raj Patel") == "raj patel"
    assert tagging.normalize("Doctor   Raj Patel") == "raj patel"
    assert tagging.normalize("Drew Barry") == "drew barry"                # "Dr" inside a name stays
    assert tagging.normalize("Mrs.Park") == "mrs.park"                    # needs a space after the title


def test_hundred_plus_pseudonyms_still_unique():
    p = tagging.Pseudonyms()
    tags = [p.get("LOC", f"Town {i}") for i in range(120)]
    assert len(set(tags)) == 120 and tags[99] == "[LOC_100]"


# ---------- pseudonymize ----------

def test_masked_replaced_unmasked_kept():
    text = "Jane Doe takes apixaban."
    flags = flags_for(text, [("Jane Doe", "PATIENT"), ("apixaban", "DRUG")])
    flags[1]["masked"] = False
    assert tagging.pseudonymize(text, flags) == "[PATIENT_01] takes apixaban."


def test_nothing_masked_changes_nothing():
    text = "Jane Doe takes apixaban."
    assert tagging.pseudonymize(text, flags_for(text, [("Jane Doe", "PATIENT")], masked=False)) == text


def test_repeats_any_case_are_replaced():
    text = "Seen in Tofino. TOFINO clinic. tofino ferry."
    out = tagging.pseudonymize(text, flags_for(text, [("Tofino", "LOC")]))
    assert out == "Seen in [LOC_01]. [LOC_01] clinic. [LOC_01] ferry."


def test_repeats_are_whole_words_only():
    text = "Lives in Hope. Hopeful about rehab."
    assert tagging.pseudonymize(text, flags_for(text, [("Hope", "LOC")])) == "Lives in [LOC_01]. Hopeful about rehab."


def test_repeat_of_value_starting_with_punctuation_is_replaced():
    # A phone written "(250) 555-0142" twice: the second copy must not leak.
    text = "Call (250) 555-0142. If no answer, (250) 555-0142 again."
    out = tagging.pseudonymize(text, flags_for(text, [("(250) 555-0142", "PHONE")]))
    assert "555-0142" not in out, out


def test_repeat_inside_an_unmasked_flag_is_still_replaced():
    # The clinician unmasked a long description that contains a masked town. The town still goes.
    text = "Lives in Hope, in the red house beside the Hope community hall."
    flags = flags_for(text, [("Hope", "LOC"), ("the red house beside the Hope community hall", "LOC")])
    flags[1]["masked"] = False
    assert "Hope" not in tagging.pseudonymize(text, flags)


def test_unicode_names():
    text = "Zoë Côté-Nguyen, seen by Dr. Siobhán Ó Briain."
    flags = flags_for(text, [("Zoë Côté-Nguyen", "PATIENT"), ("Siobhán Ó Briain", "PROVIDER")])
    out = tagging.pseudonymize(text, flags)
    assert out == "[PATIENT_01], seen by Dr. [PROVIDER_01]."
    assert tagging.restore(out, tagging.mapping_of(flags)) == text


def test_mapping_has_masked_flags_only():
    text = "Jane Doe takes apixaban."
    flags = flags_for(text, [("Jane Doe", "PATIENT"), ("apixaban", "DRUG")])
    flags[1]["masked"] = False
    assert tagging.mapping_of(flags) == {"[PATIENT_01]": "Jane Doe"}


def test_no_masked_value_survives_on_sample_note():
    text = open("sample_note.txt").read()
    items = [("Margaret Ellison", "PATIENT"), ("9123 947 241", "HCN"), ("03/14/1951", "DATE"),
             ("211 Campbell St", "ADDRESS"), ("Tofino", "LOC"), ("V0R 2Z0", "ADDRESS"),
             ("(250) 555-0142", "PHONE"), ("Claire", "FAMILY"), ("claire.ellison@example.com", "EMAIL"),
             ("Raj Patel", "PROVIDER")]
    flags = flags_for(text, items)
    out = tagging.pseudonymize(text, flags)
    for value, _ in items:
        assert value.lower() not in out.lower(), f"leaked: {value}"
    assert "Parkinson's" in out and "nitrofurantoin 100 mg BID" in out
    assert tagging.restore(out, tagging.mapping_of(flags)) == text


# ---------- restoring ----------

def test_restore_handles_altered_pseudonyms():
    m = {"[PATIENT_01]": "Jane Doe"}
    for variant in ["[PATIENT_01]", "PATIENT_01", "[Patient 01]", "[ PATIENT_01 ]", "patient_01",
                    "[PATIENT_1]", "PATIENT_1", "[Patient 1]"]:
        assert tagging.restore(f"Dear {variant}, thanks.", m) == "Dear Jane Doe, thanks.", variant


def test_restore_leaves_unknown_and_invented_pseudonyms():
    m = {"[PATIENT_01]": "Jane Doe"}
    assert tagging.restore("[PATIENT_03] and [HCN_09]", m) == "[PATIENT_03] and [HCN_09]"


def test_restore_leaves_ordinary_text_alone():
    m = {"[PATIENT_01]": "Jane Doe", "[DATE_02]": "2026-09-02"}
    text = "Type 2 diabetes, COVID 19 vaccine, Day 5, step 1, ICD 10, Apixaban 5 mg."
    assert tagging.restore(text, m) == text


def test_restore_does_not_confuse_1_and_10():
    m = {f"[PATIENT_{i:02d}]": f"Name{i}" for i in range(1, 12)}
    assert tagging.restore("[PATIENT_10] [PATIENT_01] [PATIENT_11]", m) == "Name10 Name1 Name11"


def test_restore_never_crashes_on_junk():
    m = {"[PATIENT_01]": "Jane Doe"}
    for junk in ["", "[", "]", "[[PATIENT_01]]", "[PATIENT_]", "[_1]", "\x00", "[PATIENT_99999999999999999999]"]:
        tagging.restore(junk, m)


# ---------- tagging the clinician's question ----------

def test_question_names_are_tagged_any_case():
    m = {"[PATIENT_01]": "Jane Doe", "[PATIENT_02]": "Jane"}
    assert tagging.tag_question("How is JANE DOE doing?", m) == "How is [PATIENT_01] doing?"


def test_question_tagging_is_whole_words_only():
    # A short masked value ("94", an age) must not eat parts of other numbers or words.
    m = {"[AGE_01]": "94", "[LOC_01]": "Hope"}
    q = "Give 940 mg? Hopeful plan for the 94 year old in Hope."
    assert tagging.tag_question(q, m) == "Give 940 mg? Hopeful plan for the [AGE_01] year old in [LOC_01]."


if __name__ == "__main__":
    run(globals())
