"""
Layer 1 (Presidio + BC rules) and the last-resort leak check.
Run from the backend folder:   python -m tests.test_rules
"""
import config
from pipeline import rules
from tests._util import run


def found(text: str) -> dict[str, str]:
    """{span text: type} for everything rules.find() flags. Presidio can return several types
    for the same text (a PHN is also a PHONE guess); keep the one merge.py would pick."""
    best: dict[str, dict] = {}
    for s in rules.find(text):
        t = text[s["start"]:s["end"]]
        if t not in best or (s["type"] in config.STRUCTURED_TYPES, s["score"]) > \
                (best[t]["type"] in config.STRUCTURED_TYPES, best[t]["score"]):
            best[t] = s
    return {t: s["type"] for t, s in best.items()}


# ---------- BC PHN check digit ----------

def test_phn_valid_formats():
    for v in ["9123947241", "9123 947 241", "9123-947-241"]:
        assert rules.is_valid_phn(v), v


def test_phn_rejects_bad_numbers():
    for v in ["9123947242",          # wrong check digit
              "8123947241",          # must start with 9
              "912394724",           # 9 digits
              "91239472411",         # 11 digits
              "", "abcdefghij"]:
        assert not rules.is_valid_phn(v), v


def test_phn_check_digit_10_or_11_is_never_valid():
    # Find 9-prefixed numbers whose mod-11 result is 10 or 11: no last digit can make them valid.
    weights = [2, 4, 8, 5, 10, 9, 7, 3]
    for n in range(100000, 100500):
        body = "9" + f"{n:08d}"
        check = 11 - (sum(int(body[i + 1]) * w for i, w in enumerate(weights)) % 11)
        if check >= 10:
            assert not any(rules.is_valid_phn(body + str(d)) for d in range(10)), body
            return
    raise AssertionError("no check-10/11 example found in range")


def test_find_flags_valid_phn_only():
    f = found("PHN: 9123 947 241. Old card 9123 947 242.")
    assert f.get("9123 947 241") == "PHN"
    assert f.get("9123 947 242") != "PHN"


# ---------- other structured identifiers ----------

def test_find_postal_phone_email():
    f = found("Lives at V0R 2Z0. Call (250) 555-0142 or email jo.doe@example.com today.")
    assert f.get("V0R 2Z0") == "POSTAL"
    assert f.get("(250) 555-0142") == "PHONE"
    assert f.get("jo.doe@example.com") == "EMAIL"


def test_postal_rejects_impossible_first_letters():
    # Canadian postal codes never start with D, F, I, O, Q, U, W or Z.
    for code in ["D0R 2Z0", "W1A 1A1", "Z9Z 9Z9"]:
        assert found(f"Code {code} here.").get(code) != "POSTAL", code


def test_find_facility_from_list():
    assert found("Seen at Royal Columbian Hospital overnight.").get("Royal Columbian Hospital") == "FACILITY"


def test_find_real_dates():
    f = found("Admitted 2026-09-02. DOB 03/14/1951. Seen on Sept 28.")
    for d in ["2026-09-02", "03/14/1951"]:
        assert f.get(d) == "DATE", (d, f)
    assert any("Sept 28" in t and ty == "DATE" for t, ty in f.items()), f


def test_find_dates_spacy_misses():
    for text, date in [("Seen on Sep 28.", "Sep 28"), ("seen on 28 Sept", "28 Sept"), ("Sept. 28th visit", "Sept. 28th"),
                       ("Admitted September 21, 2026 and again on Sep 28.", "September 21, 2026")]:
        assert found(text).get(date) == "DATE", (text, found(text))
    assert found("Admitted September 21, 2026 and again on Sep 28.").get("Sep 28") == "DATE"


def test_date_finder_skips_non_dates():
    for text in ["she may 2x her dose", "for 7 days", "day 5 of antibiotics", "BP 120/80",
                 "apixaban 5 mg BID", "follow up in 2 weeks"]:
        assert "DATE" not in found(text).values(), (text, found(text))


def test_find_street_addresses():
    for text, addr in [("Lives at 4820 Marine Ave in town.", "4820 Marine Ave"),
                       ("Home: 12 Old Bridge Road, Hope.", "12 Old Bridge Road"),
                       ("Mail to 1050-3 Fraser St. today", "1050-3 Fraser St.")]:
        assert found(text).get(addr) == "ADDRESS", (text, found(text))


def test_address_rule_skips_doses_durations_and_doctors():
    for text in ["apixaban 5 mg BID", "Follow up with Dr. Singh in 2 weeks.", "Seen by Dr. Amrit Singh",
                 "gave 2 Dr", "walks 2 blocks to the store"]:
        assert "ADDRESS" not in found(text).values(), (text, found(text))


def test_find_prescriber_licenses():
    for text, number in [("Signed, CPSBC #34567", "34567"), ("License: 12345", "12345"),
                         ("prescriber no. AB1234 on file", "AB1234"), ("College ID 40912", "40912")]:
        assert found(text).get(number) == "LICENSE", (text, found(text))
    assert "LICENSE" not in found("licensed practical nurse, 5 mg daily").values()


def test_scores_are_not_dates():
    for text in ["Pain 7/10 at rest.", "He rates pain 8/10 today.", "power 4/5 in the left arm", "VAS 3/10 overnight",
                 "Reports 6/10 pain", "GCS 14/15 on arrival", "Pain was 7/10, now 3/10."]:
        assert "DATE" not in found(text).values(), (text, found(text))


def test_dates_near_score_rules_are_still_dates():
    for text, date in [("Seen on 9/10 for follow-up.", "9/10"), ("Pt admitted 3/14 with chest pain.", "3/14"),
                       ("DOB 03/14/1951.", "03/14/1951"), ("Seen 9/28/2026.", "9/28/2026")]:
        assert found(text).get(date) == "DATE", (text, found(text))


# ---------- durations and relative days are clinical, not dates ----------

def test_durations_are_not_dates():
    for t in ["7 days", "2 weeks", "3 months", "10 years", "48 hours", "a week", "several days",
              "day 5", "Day 12", "POD 2", "post-op day 3", "daily", "today", "yesterday",
              "74-year-old", "3-year-old"]:
        assert not rules._is_real_date(t), t


def test_lone_numbers_and_times_are_not_dates():
    # Presidio tags question numbers and counts as dates ("2. Question", "28 patients").
    for t in ["2", "3", "28", "2026", "10:30", "4.2", "2-3", "1990s", "summary", "primary care"]:
        assert not rules._is_real_date(t), t


def test_find_ignores_numbered_questions():
    text = "2. Question: what is the mean? 3. Question: s = 4.2. Answer 4."
    assert "DATE" not in found(text).values(), found(text)


def test_real_dates_are_dates():
    for t in ["2026-09-02", "03/14/1951", "3/14", "03-14-1951", "Sept 28", "September 28, 2026",
              "Mar 3", "Mar. 3", "28 Sept", "Oct 3", "Aug 19"]:
        assert rules._is_real_date(t), t


def test_find_keeps_durations_in_a_sentence():
    text = "Nitrofurantoin 100 mg BID x 7 days, catheter removed day 5, follow up in 2 weeks."
    f = found(text)
    for t in ["7 days", "day 5", "2 weeks"]:
        assert t not in f, (t, f)


# ---------- last-resort leak check before Gemini ----------

def test_leak_check_blocks_raw_phn_and_email():
    assert rules.looks_unsafe("PHN 9123947241") == "raw PHN found"
    assert rules.looks_unsafe("PHN 9123 947 241") == "raw PHN found"
    assert rules.looks_unsafe("PHN:9123-947-241.") == "raw PHN found"
    assert rules.looks_unsafe("write to jo.doe@example.com") == "raw email found"


def test_leak_check_allows_tagged_text():
    assert rules.looks_unsafe("[PERSON_1], PHN [PHN_1], email [EMAIL_1]. Apixaban 5 mg.") is None
    assert rules.looks_unsafe("Ref 9123947242 is not a PHN (bad check digit).") is None


def test_leak_check_catches_phn_with_dots():
    # A PHN typed as 9123.947.241 is still a PHN.
    assert rules.looks_unsafe("PHN 9123.947.241") == "raw PHN found"


if __name__ == "__main__":
    run(globals())
