"""
Pseudonyms (real value -> [PATIENT_01]), pseudonymizing, and restoring Gemini's answer.
Run from the backend folder:   python -m tests.test_tagging
"""
from datetime import date

from pipeline import tagging
from pipeline.dates import shift_date
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


def test_restore_swaps_shifted_dates_back():
    m = {"[PATIENT_01]": "Jane Doe", "Aug 13": "Sept 28", "2026-08-13": "2026-09-28"}
    out = tagging.restore("[PATIENT_01] admitted Aug 13 (2026-08-13). Aug 135 is not a date.", m)
    assert out == "Jane Doe admitted Sept 28 (2026-09-28). Aug 135 is not a date."


def test_restore_never_replaces_a_restored_value_again():
    # A real date that is also another date's shifted value must not be swapped twice.
    m = {"Aug 13": "Sept 28", "Sept 28": "Nov 12"}
    assert tagging.restore("Aug 13 then Sept 28", m) == "Sept 28 then Nov 12"


# ---------- date shifting ----------

TODAY = date(2026, 10, 4)


def test_shift_keeps_the_written_style():
    cases = {"Sept 28": "Aug 13", "Sep. 28": "Aug. 13", "September 28, 2026": "August 13, 2026",
             "28 Sept 2026": "13 Aug 2026", "Mar 14, 1951": "Jan 27, 1951", "2026-09-28": "2026-08-13",
             "09/28/2026": "08/13/2026", "9/28": "8/13", "03-14-1951": "01-27-1951", "3/14/51": "1/27/51",
             "28/09/2026": "13/08/2026", "Sept 28th": "Aug 13th", "SEPT 28": "AUG 13", "Oct 12": "Aug 27"}
    for original, shifted in cases.items():
        assert shift_date(original, -46, TODAY) == shifted, (original, shift_date(original, -46, TODAY))


def test_shift_keeps_intervals():
    a, b = shift_date("2026-09-21", -46, TODAY), shift_date("2026-09-28", -46, TODAY)
    assert (date.fromisoformat(b) - date.fromisoformat(a)).days == 7
    assert shift_date("Sept 2", -46, TODAY) == "Jul 18" and shift_date("Sept 9", -46, TODAY) == "Jul 25"


def test_shift_crosses_month_and_year():
    assert shift_date("Jan 10, 2026", -46, TODAY) == "Nov 25, 2025"
    assert shift_date("Jan 10", -46, TODAY) == "Nov 25"                  # no year written, none added


def test_unreadable_dates_return_none():
    for junk in ["Sept 28 at 10:00", "Feb 30", "13/13", "2-3", "Sept 2026", "Monday", "", "day 5", "99/99/9999"]:
        assert shift_date(junk, -46, TODAY) is None, junk


# ---------- tagging the clinician's question ----------

def typed(value, kind, pseudonym, masked=True):
    """A flag as the API keeps it: value, internal type, pseudonym (position doesn't matter here)."""
    return {"text": value, "type": kind, "pseudonym": pseudonym, "masked": masked, "start_idx": 0, "end_idx": 0}


def test_question_names_are_tagged_any_case():
    flags = [typed("Jane Doe", "PERSON", "[PATIENT_01]"), typed("Jane", "PERSON", "[PATIENT_02]")]
    assert tagging.tag_question("How is JANE DOE doing?", flags) == "How is [PATIENT_01] doing?"


def test_question_tagging_is_whole_words_only():
    # A short masked value ("94", an age) must not eat parts of other numbers or words.
    flags = [typed("94", "AGE", "[AGE_01]"), typed("Hope", "LOCATION", "[LOC_01]")]
    q = "Give 940 mg? Hopeful plan for the 94 year old in Hope."
    assert tagging.tag_question(q, flags) == "Give 940 mg? Hopeful plan for the [AGE_01] year old in [LOC_01]."


def test_question_unmasked_values_stay():
    flags = [typed("Hope", "LOCATION", "[LOC_01]", masked=False)]
    assert tagging.tag_question("Lives in Hope", flags) == "Lives in Hope"


# ---------- name and number variants (QA: these reached Gemini unchanged) ----------

OKAFOR = [typed("Daniel Okafor", "PERSON", "[PATIENT_01]"), typed("Dr. Priya Sandhu", "PROVIDER", "[PROVIDER_01]"),
          typed("(604) 555-0187", "PHONE", "[PHONE_01]"), typed("9487 312 652", "PHN", "[HCN_01]")]


def test_question_variants_are_tagged():
    cases = {
        "Summarize Mr. Okafor's case": "Summarize Mr. [PATIENT_01]'s case",
        "Patient okafor, daniel - summarize": "Patient [PATIENT_01], [PATIENT_01] - summarize",
        "Was Dr. Sandhu involved?": "Was Dr. [PROVIDER_01] involved?",
        "Call 604-555-0187": "Call [PHONE_01]",
        "Call 6045550187 or (604) 555-0187": "Call [PHONE_01] or [PHONE_01]",
        "PHN 9487312652": "PHN [HCN_01]",
    }
    for q, want in cases.items():
        assert tagging.tag_question(q, OKAFOR) == want, (q, tagging.tag_question(q, OKAFOR))


def test_number_variants_need_the_whole_number():
    assert tagging.tag_question("Dose 6045550 mg, ref 46045550187", OKAFOR) == "Dose 6045550 mg, ref 46045550187"


def test_note_repeats_of_name_parts_and_number_layouts_are_replaced():
    text = ("Daniel Okafor seen by Dr. Priya Sandhu. Phone (604) 555-0187. Mr. Okafor's wife called "
            "6045550187. Discussed with Sandhu. OKAFOR to return.")
    flags = []
    for f in OKAFOR[:3]:
        start = text.index(f["text"])
        flags.append({**f, "start_idx": start, "end_idx": start + len(f["text"])})
    out = tagging.pseudonymize(text, flags)
    for secret in ["okafor", "daniel", "sandhu", "priya", "555", "0187"]:
        assert secret not in out.lower(), (secret, out)
    assert "Mr. [PATIENT_01]'s wife" in out


def test_full_value_wins_over_another_names_word():
    # "Claire Park" is flagged only in its second mention; the first is found as a repeat and
    # must become [PATIENT_02], not "Claire [PATIENT_01]" from the word "Park" of "Eleanor Park".
    text = "Eleanor Park lives with Claire Park. Later Claire Park and Park visit."
    s = text.rindex("Claire Park")
    flags = [{**typed("Eleanor Park", "PERSON", "[PATIENT_01]"), "start_idx": 0, "end_idx": 12},
             {**typed("Claire Park", "PERSON", "[PATIENT_02]"), "start_idx": s, "end_idx": s + 11}]
    out = tagging.pseudonymize(text, flags)
    assert out == "[PATIENT_01] lives with [PATIENT_02]. Later [PATIENT_02] and [PATIENT_01] visit.", out


def test_name_words_skip_titles_particles_and_eponyms():
    assert tagging._name_words("Mrs. Eleanor Park") == ["Eleanor", "Park"]
    assert tagging._name_words("Ludwig van der Berg") == ["Ludwig", "Berg"]
    assert tagging._name_words("Okafor's") == ["Okafor"]
    assert tagging._name_words("Daughter Claire") == ["Claire"]
    assert tagging._name_words("Al Wu") == []                 # too short to match safely on their own
    assert tagging._name_words("Bell") == []                  # never-redact eponym


if __name__ == "__main__":
    run(globals())
