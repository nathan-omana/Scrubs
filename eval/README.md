# Eval

Measures how many identifiers leak and how many clinical terms get wrongly removed, for default Presidio vs our pipeline (CLAUDE.md section 13). The pitch number comes from here.

**All notes are synthetic.** Every name, number and story is made up. Phone numbers use 555, emails use example.com, PHNs are random numbers that pass the BC check digit. Never add real patient data, not even "anonymized" real notes.

## Files

| Path | What |
|---|---|
| `annotated/*.txt` | The source of truth. Notes with inline labels: `[[the retired town pharmacist\|Unique role]]` |
| `notes/*.txt`, `labels/*.json` | Built from `annotated/` by `build.py`. Don't edit by hand. Labels are `[{start, end, label, tier, text}]` |
| `split.json` | 5 tuning notes (Krish may tune on these), 20 held-out test notes (nobody tunes on these) |
| `run.py` | Runs the systems and prints the table |
| `results/*.json` | Numbers from the last run of each set |

## Run

From the repo root, with the backend's Python environment (needs Presidio, spaCy `en_core_web_sm`, GLiNER):

```
python eval/build.py              # after editing annotated/
python eval/run.py                # held-out test set: the pitch number
python eval/run.py --details      # plus per-label recall and every miss
python eval/run.py --set tuning   # for tuning
```

The first run downloads the GLiNER model (a few hundred MB). Set `USE_GLINER=0` to run without it (then "ours" is rules + lexicon only).

## How to label

Label every identifier, even ones you expect the pipeline to miss. A missed label is a measured leak, which is the point.

**HIGH**
- `Person`: any person's name, including providers and relatives. Include titles ("Mrs. Eleanor Park", "Dr. Amrit Singh"). First names alone count ("Wife Grace" → label "Grace").
- `PHN`, `MRN`, `License` (prescriber or practitioner number, without the "#")
- `Address`: street address and postal code, labeled separately ("418 Ridgeview Crescent", "V0X 1L0")
- `Phone`, `Email`

**MED**
- `Date`: any date with a day or month ("Sept 28", "2026-09-21", "Oct 3"). Not years alone, not durations ("2 weeks", "day 4"), not times.
- `Age`: only ages over 89. Ages 89 and under are not labeled.
- `Location description`: towns, facilities, clinics and descriptions of places ("the last farmhouse on Lower Nicola Road past the rodeo grounds"). Big cities are labeled too, since any place narrows identity.
- `Unique role`: occupations and roles of the patient ("the retired town pharmacist", "head chef").
- `Family detail`: a relative described with something identifying ("a nurse at Fraser Canyon Hospital", "the twin brother of our clinic manager"). A bare "daughter" is not labeled.
- `Employer`: a named workplace or company ("Alpine Crest Lodge").
- `Person description`: physical or distinctive descriptions ("large raven tattoo across his neck").

**LOW** (clinical terms that must be kept)
- `Drug` (including brand names that look like names: Allegra, Lyrica, Sinemet), `Dose`, `Diagnosis` (including eponyms: Bell's palsy, Crohn's disease, Parkinson's disease, Down syndrome), `Lab value` (test plus result: "HbA1c 9.1%"), `Clinical term` (eponym devices and procedures: Foley catheter).

**Spans don't nest.** When a name sits inside a description, label the name and the rest separately: `Her son [[Marek|Person]], [[who manages the gas station on Tranquille Road|Family detail]]`.

## What the hard cases test

- Indirect identifiers Presidio has no type for: roles, family details, place descriptions, person descriptions.
- BC formats: PHNs with spaces, Canadian postal codes, MRNs, CPSBC and MSP practitioner numbers.
- Eponyms and name-like drug brands that must not be removed.
- Ambiguous town names that are also words or surnames: Hope, Nelson, Delta, Mackenzie, Yale.
- Messy formats: lowercase triage shorthand, "SURNAME, Given" headers, emails, lists, SBAR.
