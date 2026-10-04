"""
Date shifting (CLAUDE.md section 8). A masked date is replaced by the same date moved by a fixed
number of days, so intervals between dates stay correct ("admitted Sept 28, follow up Oct 12"
is still 14 days apart). The offset itself lives only in the API process's memory.

Written in the original style: "Sept 28" -> "Aug 13", "2026-09-28" -> "2026-08-13",
"09/28/2026" -> "08/13/2026", "28 September 2026" -> "13 August 2026". The year is shown only
if it was there. Anything we can't read confidently returns None, and the caller falls back to
a [DATE_NN] pseudonym. Stdlib only, no network.
"""
import re
from datetime import date, timedelta

_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
         "October", "November", "December"]
_ABBR = [m[:3] for m in _FULL]
_MONTHS = {**{m.lower(): i for i, m in enumerate(_FULL, 1)}, **{a.lower(): i for i, a in enumerate(_ABBR, 1)},
           "sept": 9}

_ORD = r"(?P<ord>st|nd|rd|th)?"
_YEAR = r"(?:(?P<s2>,?\s*)(?P<year>\d{4}))?"
# "Sept 28", "Sep. 28", "September 28, 2026", "Mar 14 1951", "Sept 28th"
_MONTH_FIRST = re.compile(r"(?P<mon>[A-Za-z]+)(?P<dot>\.?)(?P<s1>\s*)(?P<day>\d{1,2})" + _ORD + _YEAR)
# "28 Sept 2026", "28th September", "14 Mar. 1951"
_DAY_FIRST = re.compile(r"(?P<day>\d{1,2})" + _ORD + r"(?P<s1>\s+)(?P<mon>[A-Za-z]+)(?P<dot>\.?)"
                        r"(?:(?P<s2>,?\s+)(?P<year>\d{4}))?")
# "2026-09-28"
_ISO = re.compile(r"(?P<year>\d{4})-(?P<a>\d{1,2})-(?P<b>\d{1,2})")
# "09/28/2026", "9/28", "03-14-1951", "3/14/51". A dash needs a year: "2-3" is a range, not a date.
_NUMERIC = re.compile(r"(?P<a>\d{1,2})(?P<sep>[/-])(?P<b>\d{1,2})(?:(?P=sep)(?P<year>\d{4}|\d{2}))?")


def _ordinal(day: int) -> str:
    return "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _month_word(original: str, month: int) -> str:
    """The new month in the original's style: full or short, "Sept" if it was "Sept", same case."""
    if len(original) > 4 or original.lower() in ("june", "july"):
        word = _FULL[month - 1]
    else:
        word = "Sept" if month == 9 and original.lower() == "sept" else _ABBR[month - 1]
    return word.upper() if original.isupper() and len(original) > 1 else word.lower() if original.islower() else word


def _pad(value: int, width: int) -> str:
    return f"{value:0{width}d}"


def _full_year(year: str | None, today: date) -> int:
    if not year:
        return today.year                     # no year written: do the arithmetic in this year
    y = int(year)
    if len(year) == 2:                        # "51" -> 1951, "26" -> 2026
        y += 2000 if y <= today.year % 100 else 1900
    return y


def _read(text: str, today: date):
    """
    (shape, match, the date) for a whole date string, or None. The one place a date is read, so
    shift_date() and parse() always agree. Raises ValueError for impossible dates ("Feb 30").
    """
    t = text.strip()
    for rx in (_MONTH_FIRST, _DAY_FIRST):
        m = rx.fullmatch(t)
        if m and m["mon"].lower() in _MONTHS:
            return rx, m, date(_full_year(m["year"], today), _MONTHS[m["mon"].lower()], int(m["day"]))
    m = _ISO.fullmatch(t)
    if m:
        return _ISO, m, date(int(m["year"]), int(m["a"]), int(m["b"]))
    m = _NUMERIC.fullmatch(t)
    if m and (m["sep"] == "/" or m["year"]):
        a, b = int(m["a"]), int(m["b"])
        month, day = (b, a) if a > 12 and b <= 12 else (a, b)     # "28/09/2026"; otherwise month first
        return _NUMERIC, m, date(_full_year(m["year"], today), month, day)
    return None


def parse(text: str, today: date | None = None) -> tuple[int, int, int | None] | None:
    """(month, day, year or None if no year was written), or None if it isn't a date we can read."""
    try:
        got = _read(text, today or date.today())
    except (ValueError, OverflowError):
        return None
    if not got:
        return None
    _rx, m, d = got
    return d.month, d.day, (d.year if m["year"] else None)


def same_day(a: tuple | None, b: tuple | None) -> bool:
    """Two parse() results name the same day: month and day equal, years equal or one not written."""
    return bool(a and b and a[:2] == b[:2] and (a[2] is None or b[2] is None or a[2] == b[2]))


def shift_date(text: str, days: int, today: date | None = None) -> str | None:
    """`text` moved by `days`, written the same way, or None if it isn't a date we can read."""
    try:
        got = _read(text, today or date.today())
        if not got:
            return None
        rx, m, d = got
        d += timedelta(days)
    except (ValueError, OverflowError):        # "Feb 30", "13/13", year out of range
        return None

    if rx in (_MONTH_FIRST, _DAY_FIRST):
        day = _pad(d.day, 2 if m["day"].startswith("0") else 1) + (_ordinal(d.day) if m["ord"] else "")
        mon = _month_word(m["mon"], d.month) + m["dot"]
        year = f"{m['s2']}{d.year}" if m["year"] else ""
        return f"{mon}{m['s1']}{day}{year}" if rx is _MONTH_FIRST else f"{day}{m['s1']}{mon}{year}"
    if rx is _ISO:
        w = 2 if len(m["a"]) == 2 or len(m["b"]) == 2 else 1
        return f"{d.year}-{_pad(d.month, w)}-{_pad(d.day, w)}"
    day_first = int(m["a"]) > 12 and int(m["b"]) <= 12
    # Zero-pad if the original did ("09/28") or wrote both parts with two digits ("10/28").
    w = 2 if m["a"].startswith("0") or m["b"].startswith("0") or (len(m["a"]) == 2 and len(m["b"]) == 2) else 1
    first, second = (d.day, d.month) if day_first else (d.month, d.day)
    year = ""
    if m["year"]:
        year = m["sep"] + (_pad(d.year % 100, 2) if len(m["year"]) == 2 else str(d.year))
    return f"{_pad(first, w)}{m['sep']}{_pad(second, w)}{year}"


# ---------- Finding dates inside running text ----------
# Presidio's spaCy model misses "Sep 28" and "28 Sept", so rules.py also uses this finder, and
# tagging.py uses it to catch the same day written another way ("september 28" in a question).
# "May" only counts capitalized, so "she may 2x her dose" is never a date. Numeric dates need a
# year here: "7/10" is far more often a pain score than July 10 (Presidio still flags real ones).
_MON = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|(?-i:May)|june?|july?|aug(?:ust)?"
        r"|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
DATE_FINDER = re.compile(
    r"\b" + _MON + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b"           # Sept 28, Sep. 28th, 2026
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MON + r"\.?(?:,?\s+\d{4})?\b"            # 28 Sept 2026
    r"|\b\d{4}-\d{1,2}-\d{1,2}\b"                                                  # 2026-09-28
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"                                                # 09/28/2026
    r"|\b\d{1,2}-\d{1,2}-\d{2,4}\b",                                               # 03-14-1951
    re.IGNORECASE,
)


def find_dates(text: str) -> list[tuple[int, int]]:
    """(start, end) of every date in running text that parse() can read."""
    return [(m.start(), m.end()) for m in DATE_FINDER.finditer(text) if parse(m.group())]
