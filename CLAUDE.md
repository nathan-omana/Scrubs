# CLAUDE.md: Scrubs (StormHacks 2026)

This is the shared project context for the whole team. Read it before writing code and follow it over your own defaults. If something here conflicts with what you think is best, ask before changing direction.

---

## 0. Team, deadlines, and branches

- **Team:** Felix, Nathan, Krish, Armin.
- **Submission deadline:** Sunday Oct 4, 12:00 PM PT.
- **Internal targets:** feature freeze 9:30 AM, submitted by 11:00 AM.

| Branch | Owner | Scope |
|---|---|---|
| `Nathan` | Nathan |  shifting, tests |
| `Armin` | Armin | 
| `Krish` | Krish |
| `Felix` | Felix |
Ownership can be swapped. Update this table if it changes.

### Git rules
- `main` is always demo-able.
- Work on your feature branch. Merge small and often, and pull `main` into your branch regularly.
- Everything merged by the 9:30 AM feature freeze.
- Never commit `.env`, real PDFs, or anything containing real personal data.

---

## 1. What we are building

A privacy layer that lets healthcare professionals use AI on patient documents without exposing who the patient is.

A clinician uploads a PDF or pastes a note. The app finds sensitive details, lets the clinician review them, replaces masked details with consistent pseudonyms, sends only the pseudonymized text to Gemini, and re-identifies Gemini's answer on the clinician's screen. Gemini never sees who the patient is.

**Terminology:** this is **pseudonymization and masking**, not encryption of the document. The real-to-pseudonym mapping is what's stored encrypted. Never call the product "encryption" in the UI or pitch.

**One-line pitch:** "The AI never sees who the patient is, and we measure how identifiable what it does see is."

**Hook:** "Doctors spend hours a day on notes. AI could write them, but no hospital can paste patient records into ChatGPT. We built the layer that lets them."

Scope ruthlessly. A polished single flow beats many half-built features.

---

## 2. Problem and evidence (for the pitch and README)

- Clinicians already paste clinical text into AI tools to save time on documentation.
- Hospital systems have found staff using ChatGPT with "de-identified" notes, wrongly believing that removing names made it safe.
- Sensitive data makes up about 34.8% of employee inputs to AI tools (Cyberhaven).
- Healthcare is a top breach target. In 2026, CareCloud lost 3.75 million patient records from its AWS account, and DentaQuest's breach affected 15 million people.
- Vendors (business associates) expose the most records per breach. Our claim: anything that leaves the clinic is useless without the vault, and the vault never leaves.
- Existing tools (Presidio, AWS Comprehend) catch names and numbers, but miss indirect identifiers like "the retired town pharmacist," and they wrongly flag drug names as person names.

Cite TechCrunch and HHS figures on slides. Several AI-leak statistics come from vendor blogs.

---

## 3. Use cases

**Primary demo use case: referral letters.** A family doctor turns a visit note into a referral letter to a specialist.

Other supported prompts in chat:
- Discharge summaries
- Pre-visit chart summaries
- Shift handoff notes
- Meeting and case conference summaries
- Grouping similar cases across selected documents

**Out of scope:** calendars, scheduling, subscriptions, structured spreadsheets, searching for patients by identity.

**Demo persona:** Dr. Amrit Singh, a family physician at Hope Family Clinic in Hope, BC, referring a patient to cardiology in Vancouver.

---

## 4. Sponsor tracks and each tool's job

| Track | Job |
|---|---|
| Best MedTech | The core use case |
| Gemini API | The chatbot over pseudonymized text. Generates synthetic training and eval documents. Final leak-check pass on outbound text. Never send raw PHI to Gemini. |
| TiDB x AI | Encrypted vault of real-to-pseudonym mappings. Vector search to link name variants ("J. Smith" = "John Smith") so they get the same pseudonym. |
| Snowflake | Audit log of what was masked, what the user unmasked, and who approved it. Analytics on de-identified data only. |
| .tech domain | Deploy the app there |
| SSSS Python | Backend is Python |
| Tiger Data | Requirements not confirmed. Do not build for it until confirmed. |
| ElevenLabs | Future only (dictation). Not prioritized. |

Never bolt sponsor tech on. Each tool must do the job listed above.

---

## 5. End-to-end user flow

Three screens with a step indicator: **Upload → Review → Chat**.

1. **Upload:** the user uploads a PDF or pastes text. PDF text is extracted with pdfplumber. Skip scanned PDFs and OCR unless time allows.
2. **Pass 1, Presidio:** detects standard identifiers plus our custom recognizers.
3. **Pass 2, our model:** catches indirect identifiers Presidio misses, AND un-flags clinical terms Presidio wrongly flagged (for example a drug name read as a person name).
4. **Pass 3, clinical term detection:** drug names, doses, diagnoses, and lab values are labeled LOW so the user can see them, but they are kept by default.
5. **Name linking:** TiDB vector search links name variants so they share one pseudonym.
6. **Review:** the document is shown with spans highlighted by severity. The user masks or unmasks per item, within the rules in section 6.
7. **Pseudonymize:** masked values become consistent pseudonyms. Dates are shifted by a per-patient offset. The mapping goes to the encrypted vault in TiDB. Every mask and unmask decision goes to the Snowflake audit log.
8. **Chat:** the user selects reviewed documents and asks Gemini something like "Draft a referral letter to cardiology." Only pseudonymized text is sent.
9. **Leak check (Should):** before sending, Gemini scans the outbound text for any identifiers we missed. If anything is found, sending is blocked and the user is shown what was found.
10. **Re-identification:** the answer is re-identified on the client. The clinician sees real names, and Gemini never does.
11. **Split view:** the demo shows "What the AI saw" next to "What you see."

**Future (not prioritized):** ElevenLabs dictation as a third input option.

---

## 6. Severity model

| Tier | What it covers | Default | User can change? |
|---|---|---|---|
| **HIGH** | Names, BC health card numbers (PHN), MRNs, prescriber license numbers, addresses, phone numbers, email | Masked | No, locked |
| **MED** | Exact dates, ages over 89, small-town locations, employers, plus indirect identifiers from our model: location descriptions, unique roles, family details, physical descriptions | Masked | Yes, can unmask |
| **LOW** | Drug names, doses, diagnoses, lab values | Kept (shown, not masked) | Yes, can mask |

Rules:
- HIGH items are always masked and cannot be unmasked.
- Drug names, doses, and diagnoses must be preserved by default. Our model's job includes removing false positives from Presidio on clinical terms.
- Ages 89 and under are not flagged on their own.
- Each flag stores a short human-readable reason, for example "3 details combined: colour, size, landmark."
- Every change from the default is written to the Snowflake audit log with who made it and when.

---

## 7. Detection details

### 7.1 Presidio
- Built-in: PERSON, PHONE_NUMBER, EMAIL_ADDRESS, DATE_TIME, LOCATION, URL.
- Custom pattern recognizers:
  - BC PHN: 10 digits, often written 9XXX XXX XXX.
  - MRN: 6 to 8 digits preceded by "MRN".
  - Prescriber license numbers.

### 7.2 Our model
- Start with **GLiNER** (zero-shot) wrapped as a Presidio `EntityRecognizer`.
- Labels: `location description`, `unique role`, `family detail`, `person description`, `employer`, `drug`, `dose`, `diagnosis`, `lab value`.
- If the Musts are done, fine-tune a token classifier (DistilBERT or DeBERTa-small, or fine-tune GLiNER) on synthetic data.
- In the pitch say "fine-tuned on synthetic clinical notes." Never claim training on real documents.

### 7.3 Training and eval data
- Synthea records and/or Gemini-written templates filled with Faker values (Canadian names, BC PHN formats, BC addresses). Labels come free from where values were inserted.
- Add hard cases on purpose: drug names that look like names, doses that look like IDs, small-town descriptions.
- Optional pretraining: ai4privacy PII-masking datasets on Hugging Face. Check the licence first.

---

## 8. Pseudonymization

- Format: `[PATIENT_01]`, `[PROVIDER_01]`, `[HCN_01]`, `[MRN_01]`, `[LICENSE_01]`, `[ADDRESS_01]`, `[PHONE_01]`, `[EMAIL_01]`, `[LOC_01]`, `[ROLE_01]`, `[FAMILY_01]`, `[EMPLOYER_01]`, `[DESC_01]`.
- Same real value gets the same pseudonym across all documents. Normalize before lookup (lowercase, strip titles like "Mrs." and "Dr."), and use TiDB vector search to link variants.
- Do not use realistic fake values. They make re-identification ambiguous and judges can't see what was masked.
- **Dates:** shift every date for a patient by one consistent random offset, so intervals stay correct. The offset is stored in the vault.
- Unmasked items stay as original text and never create a pseudonym.
- Never use bare `[NAME]`.

---

## 9. Data model

### TiDB
```
documents(id, title, source ENUM('pdf','paste'), original_text, pseudonymized_text NULL, status ENUM('needs_review','ready'), created_at)
flags(id, document_id, flag_code 'F1', start_idx, end_idx, text, label, tier ENUM('high','med','low'), reason, masked BOOL, locked BOOL)
vault(pseudonym '[PATIENT_01]', patient_key, label, original_value_encrypted, normalized_value_embedding VECTOR, created_at)
patients(patient_key, date_offset_days_encrypted)
```
- `original_value_encrypted` is encrypted at rest. The key lives in `.env` only.

### Snowflake
```
audit_log(id, document_id, flag_code, label, tier, default_masked, final_masked, changed_by, changed_at)
outbound_log(id, document_ids, sent_text, identifier_count, model, sent_at)
```
- Snowflake only ever holds de-identified data and decisions. Never original values.

---

## 10. API (FastAPI)

- `POST /documents`: PDF upload (multipart) or `{title, text}`. Runs the pipeline and returns the document with flags.
- `GET /documents`: list with status and flag counts.
- `GET /documents/{id}`: document plus flags.
- `PATCH /documents/{id}/flags/{flag_code}`: body `{masked}`. Rejected for locked HIGH flags. Writes to the audit log.
- `POST /documents/{id}/finalize`: builds `pseudonymized_text`, writes the vault, sets status `ready`.
- `GET /documents/{id}/mapping`: returns the pseudonym-to-real mapping for this document to the client, for re-identification.
- `POST /chat`: body `{document_ids, message}`. Optional leak check, then sends pseudonymized text plus the message to Gemini, logs to Snowflake, and returns `{answer_with_pseudonyms, outbound_text, identifier_count}`.

### Re-identification
- Done on the client using the mapping endpoint.
- If Gemini drops, alters, or invents a pseudonym (for example `[PATIENT_03]` that does not exist), leave it as-is and never crash.
- Shifted dates in the answer are shifted back using the patient's offset.

### Gemini
- Use the paid tier key. Free tier inputs may be used to improve Google's products. Mention this in the pitch.
- System prompt: keep pseudonyms exactly as written, never guess real values, keep all medical content.

---

## 11. UI

### 11.1 Design system: TBD
Another team member is deciding the design system. Until it's decided:
- Do not hardcode colors, fonts, or spacing. Put them in CSS variables or a theme file so they can be swapped in one place.
- Use semantic names: `--tier-high`, `--tier-med`, `--tier-low`, `--accent`, `--surface`, `--border`.

Agreed principles:
- Function-first, clinical, plain. Color only for meaning.
- No gradients, glassmorphism, sparkle icons, emoji, glowing effects, "AI-powered" badges, or decorative cards.
- Monospace for flag IDs and pseudonyms.
- Plain labels: "Mask", "Unmask", "Review".
- Tiers must be distinguishable without color alone (text tags HIGH, MED, LOW).

Reference material (not binding):
- Figma Make file: https://www.figma.com/make/cb63pirp9qzYlKaF5Dex5a/AI-Firewall-for-PHI-Scrubbing
- An earlier mockup used IBM Plex Sans and a teal accent. Not decided.
- Teammate references: NHS service manual, USWDS, DailyMed, Epic. If USWDS is chosen, do not use its government banner, flag, or seals.

### 11.2 Upload screen
- Step indicator at the top: Upload → Review → Chat.
- PDF upload area and a paste box. One primary action: "Scan document".
- List of previously scanned documents with status and flag counts.

### 11.3 Review screen (most important, keep this structure)

**Structure**
1. Step indicator, with app name on the left and clinician name and clinic on the right ("Dr. A. Singh · Hope Family Clinic").
2. Toolbar:
   - Left: document title and source line ("Visit note, Sept 28" / "PDF upload").
   - Right: flag counts by tier, a checkbox "Show what the AI sees", and a primary button "Done, open chat".
3. Two columns, stacking on mobile:
   - Left (wider): legend for HIGH, MED, LOW, and unmasked. The document shown like a page, with the label "Original document". A summary line below.
   - Right (narrower): flagged items table.

**The document always shows the ORIGINAL text** with spans highlighted by tier. It only shows pseudonyms when the toggle is on.

**Flagged item row:** a tier tag (HIGH, MED, LOW), label with flag ID in monospace ("Location description F5"), quoted original text, reason, then one action:
- HIGH: shows "Masked" with a lock, no button.
- MED: "Unmask" button (or "Mask" if unmasked).
- LOW: "Mask" button (or "Unmask" if masked).

**Interactions**
- Clicking a highlight selects its row, and clicking a row selects its highlight.
- Changing an item updates the highlight, the counts, and the audit log.
- "Show what the AI sees" swaps masked spans for their pseudonyms and shows shifted dates.
- Hover tooltip on highlights: "Location description · F5 · MED · 3 details combined".
- Summary line: "N items masked, N kept. Medications and diagnoses are kept unless you mask them."

### 11.4 Chat screen
- Left: checklist of Ready documents to include.
- Center: chat with a split view, "What the AI saw" (pseudonyms) vs "What you see" (re-identified).
- Under each answer: "Sent to Gemini: N words, 0 identifiers", expandable to show the exact outbound text.

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
At least F4, F5, and F6 must be caught by our model, not Presidio. This is the demo moment.

---

## 13. Evaluation (required, this is the pitch number)

- Held-out synthetic test set, separate from training data.
- Report, for Presidio alone vs Presidio plus our model:
  - Leak rate (recall) on identifiers, with direct and indirect reported separately.
  - Clinical terms wrongly removed (drug names, doses, diagnoses). Target zero.
- Store in `eval/notes/`, `eval/labels/`, script at `eval/run.py`.
- One before/after number goes in the pitch. Never use a placeholder number.

---

## 14. Acceptance criteria

### Must
- PDF upload (pdfplumber) and paste both work.
- Presidio plus custom recognizers detect every HIGH category.
- Our model catches F4, F5, and F6 in the demo document and un-flags drug names Presidio misreads.
- Clinical terms are LOW and kept by default.
- HIGH is locked. MED and LOW toggle correctly.
- Consistent pseudonyms across documents, and date shifting keeps intervals correct.
- Encrypted vault in TiDB. Only pseudonymized text reaches Gemini. Add a test that asserts original values are never in an outbound request.
- Snowflake audit log records every mask and unmask change.
- Gemini drafts a referral letter. Client re-identification works and survives altered pseudonyms.
- Split view "What the AI saw" vs "What you see."
- Eval script outputs the before/after numbers.
- Deployed on the .tech domain with synthetic data only.

### Should
- TiDB vector search links name variants.
- Gemini leak check before sending.
- Outbound text panel in Chat.
- Fine-tuned token classifier with before/after recall.

### Stretch
- Re-identification risk score per document (rare diagnosis plus small location equals high risk).
- Generalizing quasi-identifiers (age ranges, first 3 characters of postal code).
- Bulk mode with review turned off, where low-confidence detections are masked automatically.
- Differential privacy noise on Snowflake aggregate queries with an epsilon slider.
- ElevenLabs dictation input.
- OCR for scanned PDFs.

### Out of scope
Real patient data, authentication, multi-tenancy, images, a local LLM router.

---

## 15. Demo script (under 3 minutes)

1. One sentence: "Hospitals want AI, but can't send patient notes to it."
2. Upload the demo PDF.
3. Review: HIGH items are locked, MED items come from our model, LOW clinical terms are kept.
4. Point at "the retired town pharmacist": "Presidio missed this. One person in Hope fits that description."
5. Show that apixaban stayed, then mention Presidio sometimes reads drug names as people.
6. Click Done, ask "Draft a referral letter to cardiology."
7. Show the split view: what the AI saw vs what you see.
8. End on the eval number.

Record a backup video before judging. Every teammate must be able to explain where the vault lives and why Gemini never sees it.

**Judge Q&A**
- "Why not just Presidio?" It misses indirect identifiers and wrongly removes drug names. Show the numbers.
- "Doesn't the AI still learn something?" Yes, the clinical content, on purpose. Identifiers are pseudonymized and dates are shifted. Anything stolen from the vendor is useless without the vault.
- "Is this encryption?" No, it's pseudonymization. The mapping is what's encrypted.

---

## 16. Stack and repo layout

**Python · FastAPI · Presidio · GLiNER · Hugging Face · pdfplumber · TiDB · Snowflake · Gemini API · React/Next.js · .tech**

Hosting: frontend on Vercel (project root is the repo root), backend on Render or Railway, both on the .tech domain.

The Next.js frontend lives at the repo root (`app/`, `lib/`, `package.json`), not in a `frontend/` folder. Run it with `npm install && npm run dev` from the root.

```
backend/
  app/main.py
  app/pipeline/presidio_setup.py
  app/pipeline/model_recognizer.py
  app/pipeline/tiers.py
  app/pipeline/pseudonymize.py
  app/pipeline/date_shift.py
  app/pdf.py
  app/vault.py          TiDB, encryption
  app/linking.py        TiDB vector search
  app/audit.py          Snowflake
  app/llm.py            Gemini client, system prompt, leak check
  tests/
app/                    Next.js frontend: page.tsx, components/ (Upload, Review, Chat)
  theme.css             theme tokens for the TBD design system
lib/                    frontend API client (api.ts), types, mock data
package.json            frontend dependencies
model/
  train/  data_gen/
eval/
  notes/  labels/  run.py
data/samples/           synthetic demo PDFs only
.env.example
```

---

## 17. Data rules

- **Synthetic data only.** Never use real patient records or scraped personal data.
- Real PDFs are gitignored. Synthetic demo PDFs go in `data/samples/`.
- API keys in `.env` only (gitignored). Keep `.env.example` with variable names: `TIDB_URL`, `VAULT_KEY`, `SNOWFLAKE_*`, `GEMINI_API_KEY`.
- Never send original values or vault contents to any external API.

---

## 18. Working rules for Claude Code

- Stay on your branch's scope (section 0). Ask before changing another branch's files.
- Keep the Review screen structure in section 11.3. Ask before changing layout or flow.
- Don't make design system decisions. Use theme variables.
- UI copy and docs: plain language, no em dashes, no buzzwords.
- Small, working increments. Run tests after each step. Keep `main` demo-able.