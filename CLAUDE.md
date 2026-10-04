# CLAUDE.md: Scrubs (StormHacks 2026)

The shared source of truth for the whole team. Read it before writing code and follow it over your own defaults. If something here conflicts with what you think is best, ask the lane owner before changing direction.

**Updated Oct 4, ~1 AM:** merged with Krish's backend work. Section 0.1 lists what changed and why.

---

## 0. Team, deadlines, lanes

- **Submission deadline:** Sunday Oct 4, 12:00 PM PT.
- **Internal targets:** feature freeze 9:30 AM, video recorded by 10:30 AM, submitted by 11:00 AM.

| Lane | Owner | Branch | Owns these files |
|---|---|---|---|
| Backend and integration lead | **Krish** | `Krish` | `backend/` (except the files Nathan owns), `requirements.txt` |
| Sponsor data (TiDB + Snowflake) | **Nathan** | `Nathan` | `backend/pipeline/lexicon.py`, `backend/audit.py`, `data/lexicon_seed.csv`, `scripts/`, `TIDB_SETUP.md` |
| Frontend | **Armin** | `Armin` | `app/`, `lib/`, `package.json` |
| Evaluation, pitch, submission | **Felix** | `Felix` | `eval/`, slides, video, Devpost, .tech deployment |

Full tasks and acceptance criteria per lane are in **section 15**.

### Checkpoints (PT)

| Time | What must be on `main` |
|---|---|
| 4:00 AM | Krish: real API endpoints with the right shapes (detection may still be tuning). Nathan: `audit.py` interface (a no-op is fine). Felix: eval notes and labels. |
| 7:00 AM | Full flow works end to end on `main` against the real backend. Felix: `eval/run.py` produces numbers. |
| 9:30 AM | **Feature freeze.** Only bug fixes, demo polish, video and Devpost after this. |
| 11:00 AM | Submitted. |

### Git rules
- `main` is always demo-able.
- Work on your lane branch. Merge small and often, and pull `main` into your branch regularly.
- Krish reviews and merges anything touching `backend/`.
- Ask the owner before editing a file in someone else's lane.
- Never commit `.env`, real PDFs, or anything containing real personal data.

### 0.1 What changed in this update (and why)

| Before | Now | Why |
|---|---|---|
| Encrypted vault of mappings in TiDB | **No vault.** Documents and mappings live only in the backend's memory and the clinician's browser. Nothing is written to disk or any database. | Storing identifiers in a cloud database, even encrypted, contradicts the pitch. No stored mapping means nothing to steal. |
| TiDB = vault + vector name linking | **TiDB = public BC lexicon** (towns, facilities, identifying occupations). The backend downloads it read-only and matches locally. | A real job for TiDB that never sends patient data up. The database enforces it with a read-only user. |
| TiDB vector search links name variants | **Name variants are linked locally** (normalize, strip titles, match surnames). Vector search is used offline to grow the lexicon from public data. | Embedding patient names in TiDB would send identifiers to the cloud. |
| FastAPI | **Flask** | The backend is already built and tested in Flask. Same routes and shapes as section 10. |
| Snowflake `outbound_log.sent_text` | **Counts only** (word count, identifier count, model). No text. | Snowflake holds decisions and counts, never text. |
| Our model = GLiNER zero-shot | GLiNER **medium** + **BC lexicon** + Presidio custom recognizers | Testing showed GLiNER small missed names and occupations. |

---

## 1. What we are building

A privacy layer that lets healthcare professionals use AI on patient documents without exposing who the patient is.

A clinician uploads a PDF or pastes a note. The app finds sensitive details, lets the clinician review them, replaces masked details with consistent pseudonyms, sends only the pseudonymized text to Gemini, and re-identifies Gemini's answer on the clinician's screen. Gemini never sees who the patient is.

**Terminology:** this is **pseudonymization and masking**, not encryption. Never call the product "encryption" in the UI or pitch.

**One-line pitch:** "The AI never sees who the patient is, and we measure how identifiable what it does see is."

**Hook:** "Doctors spend hours a day on notes. AI could write them, but no hospital can paste patient records into ChatGPT. We built the layer that lets them."

Scope ruthlessly. A polished single flow beats many half-built features.

---

## 2. Problem and evidence (for the pitch and README)

- Clinicians already paste clinical text into AI tools to save time on documentation.
- Hospital systems have found staff using ChatGPT with "de-identified" notes, wrongly believing that removing names made it safe.
- Sensitive data makes up about 34.8% of employee inputs to AI tools (Cyberhaven).
- Healthcare is a top breach target. In 2026, CareCloud lost 3.75 million patient records from its AWS account, and DentaQuest's breach affected 15 million people.
- Vendors expose the most records per breach. Our claim: anything that leaves the clinic is useless without the mapping, and the mapping never leaves the clinic.
- Existing tools (Presidio, AWS Comprehend) catch names and numbers, but miss indirect identifiers like "the retired town pharmacist," and they wrongly flag drug names as person names. Presidio has no BC PHN support.
- BC context: since 2021, BC public bodies may store personal information outside Canada (FIPPA s.33.1), but sensitive information needs a privacy impact assessment. We reduce sensitivity and volume. Never claim cloud AI is "illegal."

Cite TechCrunch and HHS figures on slides. Several AI-leak statistics come from vendor blogs.

---

## 3. Use cases

**Primary demo use case: referral letters.** A family doctor turns a visit note into a referral letter to a specialist.

Other supported prompts: discharge summaries, pre-visit chart summaries, shift handoff notes, case conference summaries, grouping similar cases across selected documents.

**Out of scope:** calendars, scheduling, subscriptions, structured spreadsheets, searching for patients by identity.

**Demo persona:** Dr. Amrit Singh, a family physician at Hope Family Clinic in Hope, BC, referring a patient to cardiology in Vancouver.

---

## 4. Sponsor tracks and each tool's job

| Track | Job | Lane |
|---|---|---|
| Best MedTech / Grand Prize | The core use case | All |
| Gemini API | The chatbot over pseudonymized text. Optional leak check on outbound text. Generates synthetic training data. Never send raw PHI to Gemini. | Krish |
| TiDB | Public BC lexicon pulled down read-only and matched locally ("hospitals pull rules down, nothing goes up"). Optional: vector search to grow the lexicon from public data. | Nathan |
| Snowflake | Audit log of mask and unmask decisions, and counts-only outbound log. Analytics on decisions only. Optional: Cortex as a second chat model. | Nathan |
| .tech domain | Public demo site, synthetic data only | Felix |
| SSSS Python | Backend is Python | Krish |
| Tiger Data, ElevenLabs, Solana | Not building | |

Never bolt sponsor tech on. Each tool must do the job listed above.

---

## 5. End-to-end user flow

Three screens with a step indicator: **Upload, Review, Chat**.

1. **Upload:** PDF (pdfplumber, in memory) or pasted text. Skip scanned PDFs.
2. **Pass 1, Presidio + BC rules:** names, phone, email, dates, BC PHN with check digit, postal codes, MRN, prescriber license.
3. **Pass 2, our model (GLiNER):** indirect identifiers (location descriptions, unique roles, family details, person descriptions, employers) plus clinical terms (drug, dose, diagnosis, lab value) labeled LOW.
4. **Pass 3, BC lexicon (from TiDB, matched locally):** known BC towns, facilities, identifying occupations.
5. **Merge:** combine all passes. Drop clinical eponyms ("Parkinson's", "Foley") from person flags. Link name variants locally.
6. **Review:** the clinician masks or unmasks within the rules in section 6. Every change goes to the Snowflake audit log.
7. **Pseudonymize (finalize):** masked values become consistent pseudonyms. Dates shift by one offset per patient. The mapping stays in memory.
8. **Chat:** only pseudonymized text goes to Gemini.
9. **Leak check:** before sending, check that no original value of a masked flag (and no raw PHN or email) is in the outbound text. If found, block and show what was found.
10. **Re-identification** happens on the client using the mapping. Altered or invented pseudonyms are left as-is.
11. **Split view:** "What the AI saw" next to "What you see."

---

## 6. Severity model

| Tier | What it covers | Default | User can change? |
|---|---|---|---|
| **HIGH** | Names (patient and provider), BC PHN, MRN, prescriber license numbers, street addresses and postal codes, phone, email | Masked | No, locked |
| **MED** | Exact dates, ages over 89, small-town locations, facilities, employers, plus indirect identifiers from our model: location descriptions, unique roles, family details, person descriptions | Masked | Yes, can unmask |
| **LOW** | Drug names, doses, diagnoses, lab values | Kept (shown, not masked) | Yes, can mask |

Rules:
- HIGH items are always masked and cannot be unmasked (enforced on the server, not just the UI).
- Drug names, doses and diagnoses are preserved by default.
- Ages 89 and under are not flagged on their own.
- Each flag has a short human-readable reason, for example "3 details combined: town, role, age" or "BC PHN, check digit valid".
- Every change from the default is written to the Snowflake audit log.

---

## 7. Detection details

### 7.1 Presidio + BC rules (`backend/pipeline/rules.py`)
- Presidio is used to **find** only. Its anonymizer is never used.
- Built-in: PERSON, PHONE_NUMBER, EMAIL_ADDRESS, DATE_TIME.
- Custom: BC PHN (10 digits starting with 9, mod-11 check digit, validated against the BC MSP spec example 9123947241), Canadian postal code, MRN (6 to 8 digits after "MRN"), prescriber license.
- Durations ("7 days", "2 weeks", "day 5") are not dates.
- Presidio's email check is forced offline (it tried to download a domain list on first run).

### 7.2 Our model (`backend/pipeline/detector.py`)
- **GLiNER** `urchade/gliner_medium-v2.1` (Apache 2.0, CPU, about 0.15 s per note). It labels phrases. It is not a chatbot, so text in a note can't instruct it.
- Notes are split into chunks of about 1,200 characters, because GLiNER reads about 384 tokens at a time.
- Labels and threshold live in `backend/config.py`. Testing showed labels compete: adding "doctor" lifts provider names, and "family member" beats "family relationship". The threshold is about 0.3. Tune on Felix's eval notes, never by guessing.
- In the pitch say "fine-tuned on synthetic clinical notes" only if we actually fine-tune. Never claim training on real documents.

### 7.3 BC lexicon (`backend/pipeline/lexicon.py`, data from TiDB)
- About 330 public entries: BC communities, BC facilities, identifying occupations. `ambiguous=1` marks entries that are also common words or names (Hope, Golden, Nelson, judge). Those only count when GLiNER flags the same spot.
- Case-sensitive, whole-word, longest match first.
- Loaded once, read-only, from TiDB. Falls back to `data/lexicon_seed.csv` if TiDB is unreachable.

### 7.4 Merge (`backend/pipeline/merge.py`)
- Keep every finding from every pass (a miss is a leak, an extra flag is one click).
- Type priority on overlap: structured rule (checksum or pattern) > GLiNER > lexicon > Presidio's spaCy PERSON guess.
- Never-redact list for clinical eponyms lives in `config.py`.

### 7.5 Training and eval data
- Training: Gemini-written templates filled with Faker values (Canadian names, BC PHN formats, BC addresses). Labels come free from where values were inserted.
- Eval: written by people, not Gemini, and never used for tuning thresholds beyond the agreed tuning set (section 13).

---

## 8. Pseudonymization

Pseudonym prefixes and flag labels (the frontend shows `label`):

| Backend type | Flag `label` | Tier | Pseudonym |
|---|---|---|---|
| Patient name | Person | HIGH | `[PATIENT_01]` |
| Provider name ("Dr. ...") | Person | HIGH | `[PROVIDER_01]` |
| BC PHN | PHN | HIGH | `[HCN_01]` |
| MRN | MRN | HIGH | `[MRN_01]` |
| Prescriber license | License | HIGH | `[LICENSE_01]` |
| Street address, postal code | Address | HIGH | `[ADDRESS_01]` |
| Phone | Phone | HIGH | `[PHONE_01]` |
| Email | Email | HIGH | `[EMAIL_01]` |
| Date | Date | MED | shifted date |
| Age over 89 | Age | MED | `[AGE_01]` |
| Town, location description, facility | Location description | MED | `[LOC_01]` |
| Occupation, unique role | Unique role | MED | `[ROLE_01]` |
| Family member or detail | Family detail | MED | `[FAMILY_01]` |
| Employer | Employer | MED | `[EMPLOYER_01]` |
| Person description | Person description | MED | `[DESC_01]` |
| Drug / Dose / Diagnosis / Lab value | Drug / Dose / Diagnosis / Lab value | LOW | `[DRUG_01]` etc. only if masked |

- Same real value gets the same pseudonym across all documents in the session. Normalize before lookup (lowercase, strip titles like "Mrs." and "Dr.").
- Do not use realistic fake values. Judges need to see what was masked.
- **Dates:** shift every date for a patient by one random offset (kept in memory), so intervals stay correct.
- Unmasked items stay as original text and never create a pseudonym.
- Never use bare `[NAME]`.

---

## 9. Data model: where everything lives

| Data | Lives in | Never goes to |
|---|---|---|
| Original document text, flags, mapping, date offsets | Backend process memory (a Python dict) and the clinician's browser. Cleared on restart. | Disk, TiDB, Snowflake, Gemini, logs |
| Pseudonymized text | Backend memory, and Gemini when the user chats | Snowflake, TiDB, logs |
| BC lexicon (public) | TiDB `bc_lexicon`, plus a copy in backend memory | |
| Mask and unmask decisions | Snowflake `audit_log` | |
| Outbound counts | Snowflake `outbound_log` | |

### TiDB
```
bc_lexicon(id, phrase, type ENUM-like 'LOCATION'|'FACILITY'|'OCCUPATION', ambiguous BOOL, version, updated_at)
```
The backend connects as a read-only user (`GRANT SELECT` only).

### Snowflake
```
audit_log(id, document_id, flag_code, label, tier, default_masked, final_masked, changed_by, changed_at)
outbound_log(id, document_ids, word_count, identifier_count, model, sent_at)
```
No column ever holds original or pseudonymized text.

---

## 10. API (Flask, `backend/app.py`, default `http://127.0.0.1:5000`)

**The contract is `lib/types.ts`.** Responses must match `Doc`, `Flag` and `ChatResponse` exactly. Change shapes only with Armin.

- `POST /documents`: PDF upload (multipart `file`) or JSON `{title, text}`. Runs the pipeline and returns the `Doc` with `flags`.
- `GET /documents`: list of `Doc`.
- `GET /documents/{id}`: one `Doc`.
- `PATCH /documents/{id}/flags/{flag_code}`: body `{masked}`. Rejected (403) for locked HIGH flags. Calls `audit.log_flag_change`.
- `POST /documents/{id}/finalize`: builds `pseudonymized_text`, sets status `ready`.
- `GET /documents/{id}/mapping`: pseudonym-to-real mapping, for client re-identification.
- `POST /chat`: body `{document_ids, message}`. Tags the message, runs the leak check, sends to Gemini, calls `audit.log_outbound`, returns `ChatResponse`.
- `GET /health`: `{ok, gliner, lexicon: "tidb" | "csv" | "off"}`.

`Flag.source` is `"presidio" | "model" | "lexicon"`.

### Gemini (`backend/gemini_client.py`)
- Paid-tier key. Free-tier inputs may be used to improve Google's products. Mention this in the pitch.
- System prompt: keep pseudonyms exactly as written, never guess real values, keep all medical content.

### Audit hooks (`backend/audit.py`, owned by Nathan, called by Krish)
```python
def log_flag_change(document_id, flag_code, label, tier, default_masked, final_masked, changed_by): ...
def log_outbound(document_ids, word_count, identifier_count, model): ...
```
Both are no-ops when `SNOWFLAKE_*` is unset, never raise, and never receive text.

---

## 11. UI

### 11.1 Design system
- Colors, fonts and spacing live in `app/theme.css` as variables: `--tier-high`, `--tier-med`, `--tier-low`, `--accent`, `--surface`, `--border`.
- Function-first, clinical, plain. Color only for meaning. No gradients, glassmorphism, sparkle icons, emoji, glow or "AI-powered" badges.
- Monospace for flag IDs and pseudonyms. Plain labels: "Mask", "Unmask", "Review".
- Tiers are distinguishable without color (text tags HIGH, MED, LOW).

### 11.2 Upload screen
Step indicator, PDF upload area and paste box, one primary action "Scan document", list of previously scanned documents with status and flag counts.

### 11.3 Review screen (most important, keep this structure)
- Toolbar: document title and source; flag counts by tier; checkbox "Show what the AI sees"; primary button "Done, open chat".
- Left: legend and the **original** document with spans highlighted by tier. Pseudonyms only when the toggle is on.
- Right: flagged items table. Row: tier tag, label with flag ID in monospace, quoted text, reason, one action (HIGH: "Masked" with lock; MED: "Unmask"/"Mask"; LOW: "Mask"/"Unmask").
- Clicking a highlight selects its row and vice versa. Hover tooltip: "Location description · F5 · MED · 3 details combined".
- Summary line: "N items masked, N kept. Medications and diagnoses are kept unless you mask them."

### 11.4 Chat screen
- Left: checklist of Ready documents.
- Center: split view "What the AI saw" vs "What you see".
- Under each answer: "Sent to Gemini: N words, 0 identifiers", expandable to the exact outbound text.

---

## 12. Demo document and expected flags (seed data and test fixture)

```
Mrs. Eleanor Park, 72, MRN 4482913, was admitted on Sept 28 after a fall at her home, the small red house beside the Hope community hall. She is the retired town pharmacist, and her daughter, a nurse at Fraser Canyon Hospital, visits daily. History of atrial fibrillation. Weight 112 kg. Started on apixaban 5 mg BID. Follow up with Dr. Amrit Singh in 2 weeks.
```

| Flag | Label | Text | Tier | Default | Pseudonym |
|---|---|---|---|---|---|
| F1 | Person | Mrs. Eleanor Park | HIGH | Masked, locked | [PATIENT_01] |
| F2 | MRN | 4482913 | HIGH | Masked, locked | [MRN_01] |
| F3 | Date | Sept 28 | MED | Masked | shifted date |
| F4 | Location description | the small red house beside the Hope community hall | MED | Masked | [LOC_01] |
| F5 | Unique role | the retired town pharmacist | MED | Masked | [ROLE_01] |
| F6 | Family detail | a nurse at Fraser Canyon Hospital | MED | Masked | [FAMILY_01] |
| F7 | Diagnosis | atrial fibrillation | LOW | Kept | n/a |
| F8 | Drug | apixaban | LOW | Kept | n/a |
| F9 | Dose | 5 mg BID | LOW | Kept | n/a |
| F10 | Person | Dr. Amrit Singh | HIGH | Masked, locked | [PROVIDER_01] |

Not flagged: "72" (age 89 and under), "112 kg", "2 weeks".
F4, F5 and F6 must come from our model or lexicon (`source` "model" or "lexicon"), not Presidio. This is the demo moment.

---

## 13. Evaluation (required, this is the pitch number)

- `eval/notes/` (20+ synthetic notes written by people), `eval/labels/` (one JSON per note: `[{start, end, label, tier}]`), script `eval/run.py`.
- Use 5 notes as a **tuning set** (Krish may tune on these) and the rest as the **held-out test set** (nobody tunes on these).
- Report for Presidio alone (default `AnalyzerEngine`, no custom rules) vs our full pipeline, on the held-out set:
  - Recall on direct identifiers (HIGH) and indirect identifiers (MED), separately.
  - Clinical terms wrongly removed. Target zero.
- A span counts as caught if it overlaps a labeled span.
- One before/after number goes in the pitch. Never use a placeholder number.

---

## 14. Hard rules (every person and every Claude Code session)

1. **Never send original values anywhere outside the backend process and the clinician's browser.** Not to Gemini, Snowflake, TiDB or logs.
2. **Nothing is written to disk.** Uploads are read in memory. No database holds documents or mappings.
3. **Logs contain counts only** ("3 Person, 1 PHN"). Never print or log note text while debugging.
4. **Network calls only in:** `gemini_client.py` (pseudonymized text), `audit.py` (decisions and counts), `lexicon.py` (one read-only TiDB download). Everything else must work with Wi-Fi off.
5. **Synthetic data only.** Never real patient records, not even to test.
6. Secrets only in `.env` (gitignored). Never paste keys into a chat or commit them.
7. The backend binds to `127.0.0.1` by default. CORS allows the frontend origin only.

---

## 15. Lanes: tasks and acceptance criteria

Keep it small. Each lane's Musts come first. Don't start a Should until your Musts pass.

### Krish: backend and integration lead

**Context:** the pipeline (Presidio + GLiNER + merge + tagging + Gemini client) is built and tested in Flask, but it currently uses its own stateless endpoints, RED/YELLOW levels and `[PERSON_1]` tags. Your job is to make it speak this file's API, tiers and pseudonyms, and to integrate everyone else's work.

**Must**
1. Merge the TiDB lexicon add-on and push the backend to `main` first, so the others build on it.
2. Implement section 10 endpoints in Flask with an in-memory store, returning shapes that match `lib/types.ts`. Allow CORS from `http://localhost:3000`.
3. Convert levels to section 6 tiers, labels and pseudonyms (section 8). Flag codes F1, F2... in reading order. Locked HIGH. Ages 89 and under not flagged. A short reason per flag.
4. Add MRN and prescriber license recognizers. Add GLiNER labels for location description, unique role, family detail, person description, drug, dose, diagnosis, lab value.
5. Date shifting with one offset per patient, kept in memory.
6. `/chat`: tag the message, run the leak check, call Gemini, call `audit.log_outbound`.

**Acceptance criteria**
- [ ] `POST /documents` with the section 12 note returns F1 to F10 with the listed labels, tiers and defaults. "72", "112 kg" and "2 weeks" are not flagged. F4, F5 and F6 have `source` "model" or "lexicon".
- [ ] `PATCH` on a HIGH flag returns 403. MED and LOW toggle and call `audit.log_flag_change`.
- [ ] `finalize` produces `pseudonymized_text` containing no original value of any masked flag. Shifted dates keep the same intervals.
- [ ] A test asserts that no original masked value ever appears in a Gemini request.
- [ ] `/chat` returns a referral letter with pseudonyms when `GEMINI_API_KEY` is set, and a clear error when it isn't.
- [ ] Restarting the server clears all documents. Nothing is written to disk. Logs show counts only.
- [ ] `python -m tests.test_smoke` and `python -m tests.test_lexicon` pass.

**Should:** document-level risk ("3 details combined" escalation), Gemini leak-check pass, Snowflake Cortex as a second model.

### Nathan: sponsor data (TiDB + Snowflake)

**Context:** the lexicon code, seed data, seed and verify scripts are written and tested. Follow `TIDB_SETUP.md`. Snowflake is new work in `backend/audit.py`.

**Must**
1. TiDB: create the cluster, a seeder user and a **read-only** gateway user. Fill `.env`. Run `scripts/seed_lexicon.py`, then `scripts/verify_lexicon.py`.
2. Make sure the demo's places are covered: Hope (ambiguous), Fraser Canyon Hospital, Vancouver. Add 50+ more small BC communities and identifying occupations (public info only).
3. Snowflake: create `audit_log` and `outbound_log` (section 9). Write `backend/audit.py` with the two functions in section 10. No-op when unconfigured, never raise, never accept text.
4. Push the `audit.py` interface to `main` by 4:00 AM, even as a no-op, so Krish can call it.

**Acceptance criteria**
- [ ] `verify_lexicon.py` prints: read OK, write blocked, source `tidb`. Screenshot saved for Devpost.
- [ ] `GET /health` shows `"lexicon": "tidb"` with TiDB configured and `"csv"` without.
- [ ] Unmasking a MED flag in the UI adds one `audit_log` row. No column contains document text.
- [ ] Each chat message adds one `outbound_log` row with counts only.
- [ ] With `SNOWFLAKE_*` and `TIDB_*` unset, the whole app still works.
- [ ] One Snowflake worksheet query (decisions by tier, unmask rate) with a screenshot for Devpost.

**Should:** `scripts/expand_lexicon.py` using TiDB vector search on public phrase pools (suggestions are reviewed by a person before going into the CSV).

### Armin: frontend

**Context:** the Next.js app is built against this file's API, served by mocks in `lib/api.ts`. Krish's real endpoints land by about 4:00 AM.

**Must**
1. In `lib/api.ts`, replace each mock body with a `fetch()` to `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:5000`). Keep the mocks behind `NEXT_PUBLIC_USE_MOCK=1` for the public .tech demo and as a fallback.
2. Add `"lexicon"` to `Flag.source` and show model and lexicon finds as "Found by our model" in Review.
3. Keep the mapping in React state only. Never `localStorage` or `sessionStorage`.
4. Handle errors: backend down, locked flag (403), leak check blocked, Gemini error.

**Acceptance criteria**
- [ ] Against the real backend: upload or paste the section 12 note, see F1 to F10, toggle "Show what the AI sees", click Done, ask for a referral letter, see the split view with real names restored.
- [ ] Altered or invented pseudonyms in an answer are shown as-is, with no crash.
- [ ] Browser Network tab shows requests only to our backend (no third-party requests carrying document text).
- [ ] `npm run build` passes. Mock mode still works with one env flag.

**Should:** the outbound text panel, polish on the Review screen interactions in 11.3.

### Felix: evaluation, pitch, submission

**Context:** the eval number is the pitch. Krish needs your tuning notes early, and the held-out notes must stay untouched.

**Must**
1. By 4:00 AM: 20+ synthetic notes in `eval/notes/` written by people (varied styles, small BC towns, rare roles, family details, eponyms like Bell's palsy and Foley that must not be removed, drug names that look like names). Labels in `eval/labels/`. Mark 5 as the tuning set.
2. By 7:00 AM: `eval/run.py` comparing default Presidio vs our pipeline (import `backend/pipeline`) on the held-out set.
3. Slides, the section 16 demo script, a backup video under 3 minutes, and Devpost (with a short section per sponsor track).
4. .tech: deploy the frontend (Vercel) in mock mode with a "Synthetic data only" banner. The live demo runs from Krish's laptop.

**Acceptance criteria**
- [ ] `python eval/run.py` prints a table: recall HIGH, recall MED, clinical terms wrongly removed, for both systems. Numbers come from a real run.
- [ ] One before/after number on a slide.
- [ ] Backup video recorded by 10:30 AM.
- [ ] Devpost submitted by 11:00 AM with screenshots (including Nathan's TiDB and Snowflake screenshots) and the repo link.
- [ ] The .tech URL loads the app.

**Should:** a Gemini "attacker" that tries to re-identify the patient from Presidio's output vs ours (cleaned text only).

---

## 16. Demo script (under 3 minutes)

1. One sentence: "Hospitals want AI, but can't send patient notes to it."
2. Upload the demo note.
3. Review: HIGH items are locked, MED items come from our model and our BC lexicon, LOW clinical terms are kept.
4. Point at "the retired town pharmacist": "Presidio missed this. One person in Hope fits that description."
5. Show that apixaban stayed. Mention Presidio sometimes reads drug names as people.
6. Click Done, ask "Draft a referral letter to cardiology."
7. Split view: what the AI saw vs what you see.
8. End on the eval number.

Optional live proof: open the browser Network tab during chat, or turn Wi-Fi off to show detection still works.

**Every teammate must be able to explain where the mapping lives:** in the backend's memory on the clinic's machine and in the clinician's browser. It's never written down, never sent anywhere, and gone on restart.

**Judge Q&A**
- "Why not just Presidio?" It misses indirect identifiers, has no BC PHN, and wrongly removes drug names. Show the numbers.
- "Doesn't the AI still learn something?" Yes, the clinical content, on purpose. Identifiers are pseudonymized and dates shifted.
- "Is this encryption?" No, it's pseudonymization. And there's no stored mapping to steal.
- "Why not run a local model for everything?" Laptop-sized models are weak at clinical reasoning, so staff would go back to ChatGPT. The local model only detects. Gemini reasons.
- "Why TiDB?" Hospitals pull BC rules down and nothing goes up. The database enforces it with a read-only user.
- "Why Snowflake?" An audit trail of every privacy decision, with no patient text in it.

---

## 17. Stack and repo layout

**Python · Flask · Presidio · GLiNER · pdfplumber · TiDB · Snowflake · Gemini API · Next.js · .tech**

```
backend/
  app.py                Flask API (section 10)
  config.py             all tuning knobs: labels, threshold, lists
  gemini_client.py      Gemini (pseudonymized text only)
  audit.py              Snowflake hooks (Nathan)
  demo.py               terminal run of the pipeline
  pipeline/
    extract.py          PDF/DOCX/TXT to text, in memory
    rules.py            Presidio + BC rules, leak check
    detector.py         GLiNER
    lexicon.py          TiDB lexicon (Nathan)
    merge.py            combine passes
    risk.py             tiers and reasons
    tagging.py          pseudonyms, restore
  tests/
app/                    Next.js frontend (Armin)
lib/                    API client, types (the contract), mocks
data/lexicon_seed.csv   public lexicon, fallback copy (Nathan)
scripts/                seed_lexicon.py, verify_lexicon.py (Nathan, run by hand)
eval/                   notes, labels, run.py (Felix)
IMPLEMENTATION.md, PROCESS.md   backend design notes
TIDB_SETUP.md           TiDB guide (Nathan)
```

Run: backend `cd backend && python app.py`. Frontend `npm install && npm run dev` from the repo root.

---

## 18. Data rules and environment

- Synthetic data only. Real PDFs are gitignored. Synthetic demo files go in `data/samples/`.
- `.env.example` lists: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GLINER_MODEL`, `USE_GLINER`, `HF_HUB_OFFLINE`, `LEXICON_SOURCE`, `TIDB_HOST`, `TIDB_PORT`, `TIDB_DATABASE`, `TIDB_USER`, `TIDB_PASSWORD`, `TIDB_ADMIN_USER`, `TIDB_ADMIN_PASSWORD`, `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD` (or token), `SNOWFLAKE_DATABASE`, `SNOWFLAKE_WAREHOUSE`. Frontend: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_USE_MOCK`.
- After GLiNER downloads once, set `HF_HUB_OFFLINE=1` so it never contacts Hugging Face again.

---

## 19. Working rules for Claude Code

- Read this file first. Stay in your lane (section 0). Ask before changing files in another lane.
- Follow the hard rules in section 14 above everything else.
- Keep the Review screen structure in 11.3. Use theme variables, no design system decisions.
- Don't over-engineer: the smallest change that meets the acceptance criteria.
- UI copy and docs: plain language, no em dashes, no buzzwords.
- Small, working increments. Run tests after each step. Keep `main` demo-able.

### Starter prompts

- **Krish:** "Read CLAUDE.md. Do my lane in section 15 in order, stopping after each Must to show me results. Start by merging the TiDB lexicon add-on, then the section 10 endpoints."
- **Nathan:** "Read CLAUDE.md and TIDB_SETUP.md. I've filled TIDB_* in .env myself (don't print it). Do my lane in section 15: seed and verify TiDB, extend the lexicon, then build backend/audit.py for Snowflake. Stop after each Must."
- **Armin:** "Read CLAUDE.md, especially sections 10, 11 and 15 (Armin). Switch lib/api.ts from mocks to the real backend behind NEXT_PUBLIC_USE_MOCK, add the lexicon source, and handle errors. Stop after each Must."
- **Felix:** "Read CLAUDE.md, especially sections 12, 13 and 15 (Felix). Help me write 20+ synthetic eval notes with labels, then build eval/run.py comparing default Presidio to our pipeline. Never use real patient data."
