# Scrub In: Backend Implementation (Presidio + GLiNER + Gemini)

This document explains **what was built**: the files, how data moves through them, how to run it, and what is and isn't finished.

---

## 1. What this is

A small Python backend that takes a clinical note and:

1. **Finds** identifying details with two detectors:
   - **Presidio + BC rules** (layer 1): PHN with check digit, phone, email, dates, postal codes, BC facility names
   - **GLiNER** (layer 2): names, occupation, town, age, family relationships, employer, street address
2. **Merges** both lists into one, keeping every finding except medical terms like "Parkinson's".
3. **Scores risk** with plain rules (RED / YELLOW / GREEN, including risky *combinations*).
4. **Tags** approved findings: `Margaret Ellison` becomes `[PERSON_1]`.
5. **Sends only tagged text** to Gemini, after a last-resort safety check.
6. **Restores** real names in Gemini's answer with find-and-replace.

**GLiNER is not a chatbot.** It only labels phrases. **Gemini is the only chatbot.**

The server is **stateless**: it keeps nothing between requests. No database, no files written, and logs contain counts only.

---

## 2. Files

```
scrubin/
├── IMPLEMENTATION.md        ← this file
├── PROCESS.md               ← how and why it was built this way
├── requirements.txt
├── .env.example             ← copy to .env, add your Gemini key
├── .gitignore
└── backend/
    ├── app.py               ← Flask server: /health, /analyze, /tag, /chat
    ├── config.py            ← every setting in one place (labels, thresholds, lists)
    ├── gemini_client.py     ← the ONLY code that talks to the internet
    ├── demo.py              ← run the whole flow in the terminal, no frontend needed
    ├── sample_note.txt      ← a SYNTHETIC note for testing
    ├── pipeline/
    │   ├── __init__.py      ← analyze(text) = rules + GLiNER → merge → risk
    │   ├── extract.py       ← .txt / .pdf / .docx → text, in memory
    │   ├── rules.py         ← layer 1: Presidio + BC PHN / postal / facility rules
    │   ├── detector.py      ← layer 2: GLiNER (chunking, labels, threshold)
    │   ├── merge.py         ← combine both layers' findings
    │   ├── risk.py          ← RED / YELLOW / GREEN rules
    │   └── tagging.py       ← tag, restore, tag the clinician's question
    └── tests/
        └── test_smoke.py    ← quick checks (fakes GLiNER + Gemini, so no downloads)
```

---

## 3. How data flows

```
POST /analyze  (file or {"text"})
   │
   ├─ extract.py      file → text (in memory; uploads never spill to disk)
   ├─ rules.py        Presidio finds PHN, phone, email, dates, postal, facilities, + spaCy names
   ├─ detector.py     GLiNER finds names, occupation, town, age, relation, employer, address
   ├─ merge.py        one combined list
   └─ risk.py         levels per finding + overall risk
   ▼
returns { text, spans:[{id,start,end,type,text,level,found_by,remove_by_default}], risk }

   (clinician reviews in the frontend and picks which ids to remove)

POST /tag      { text, spans, remove_ids }
   ▼
returns { tagged_text, mapping }      ← mapping goes back to the browser and is NOT kept

POST /chat     { tagged_note, history, question }   ← all already tagged by the browser
   ├─ looks_unsafe()  blocks the request if a raw PHN or email is still present
   └─ gemini_client   sends tagged text to Gemini
   ▼
returns { answer (still tagged), sent (exactly what went out, for the request log) }

   (browser runs restore(answer, mapping) → real names shown to the clinician)
```

---

## 4. Setup and running

```bash
# 1. Python environment (Python 3.10+)
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # GLiNER pulls in PyTorch, a big download (CPU is fine)
python -m spacy download en_core_web_sm

# 2. Settings
cp .env.example .env                 # then put your GEMINI_API_KEY in .env

# 3. Try it in the terminal (first run downloads GLiNER, a few hundred MB)
cd backend
python demo.py sample_note.txt
python demo.py sample_note.txt --ask "Summarize this discharge for the patient's daughter"

# 4. Run the server for the frontend
python app.py                        # http://127.0.0.1:5000

# 5. Quick checks (no downloads, no API calls)
python -m tests.test_smoke
```

**After GLiNER has downloaded once,** set `HF_HUB_OFFLINE=1` in `.env`. From then on nothing is fetched at runtime, and only `gemini_client.py` uses the internet.

**No GLiNER yet?** Set `USE_GLINER=0` to run on rules only. It works, but it misses towns, ages, occupations and addresses.

### Try the API with curl

```bash
curl -X POST localhost:5000/analyze -F "file=@sample_note.txt"
curl -X POST localhost:5000/analyze -H "Content-Type: application/json" -d '{"text":"Pt Jane Doe, PHN 9123 947 241"}'
```

---

## 5. Where to change things

| You want to... | Edit |
|---|---|
| Add or rename GLiNER categories | `config.GLINER_LABELS` (plain English on the left, tag type on the right) |
| Catch more / fewer things | `config.GLINER_THRESHOLD` (lower = catches more) |
| Stop a medical word being redacted | `config.NEVER_REDACT` |
| Add BC hospitals | `config.BC_FACILITIES` |
| Change when a note is RED | `config.RED_COMBINATION`, `DIRECT_TYPES`, `QUASI_TYPES` |
| Use a fine-tuned GLiNER | `GLINER_MODEL=path/to/your/model` in `.env` |
| Better Presidio names | `SPACY_MODEL=en_core_web_lg` (after `python -m spacy download en_core_web_lg`) |
| Change the Gemini model or prompt | `GEMINI_MODEL` in `.env`, `SYSTEM_PROMPT` in `gemini_client.py` |

---

## 6. What was tested here, and what wasn't

**Tested** (in a sandbox; `tests/test_smoke.py` passes):

- BC PHN check digit, using the valid example `9123947241` from the BC MSP spec
- Presidio + BC rules on the sample note
- Merging, never-redact list, kept durations ("7 days", "day 5"), risk combination → RED
- Tagging leaks nothing from the sample note: name, PHN, town, phone, email and street are all gone, while "Parkinson's" and "7 days" stay
- The same value elsewhere in the note is also tagged (e.g. "Tofino" in the address and in the text)
- Restoring handles changed tags (`PERSON_1`, `[Person 1]`)
- Flask endpoints, including: uploads stay in memory, oversized text is rejected, and **a raw PHN is blocked from reaching Gemini**
- Logs contain counts only

**Not tested here:**

- **The real GLiNER model.** The sandbox couldn't reach Hugging Face to download it. The code was checked against the GLiNER library's source (`predict_entities(text, labels, threshold)` returning `start`/`end`/`label`/`score`), and the tests use a fake GLiNER. **Your first real run is the real test.** Expect different findings than the fake one, and tune labels and threshold on your eval notes.
- **A real Gemini call.** Faked in the tests. Needs your API key.

---

## 7. Deliberately not built yet

| Not built | Why / next step |
|---|---|
| Date shifting (keep intervals) | Dates are tagged `[DATE_1]` for now. Next: convert to "Day 0 / Day 7". |
| GLiNER fine-tuning | Run untrained GLiNER on the eval set first, and fine-tune only the weak labels |
| Evaluation script | Person 4: run Presidio alone vs. Presidio + GLiNER on hand-written notes |
| Frontend | Calls `/analyze` → review → `/tag` → `/chat`. Port `tagging.restore` to JS. |
| Scanned PDFs (OCR) | Returns "no text found" for now |
| Locking down CORS | Currently `*` for local development. Restrict it before any deployment. |
| Pinned versions | Run `pip freeze > requirements.lock.txt` once everything works |

---

## 8. Using this with Claude Code

Open the `scrubin/` folder in VS Code with Claude Code. A good first prompt:

> Read IMPLEMENTATION.md and PROCESS.md. Set up the venv, install requirements, download en_core_web_sm, then run `python demo.py sample_note.txt` from backend/. Show me the findings table and tell me which identifiers GLiNER missed or over-flagged. Don't change the architecture; only tune config.py.

Rules worth telling Claude Code to follow:

- Never log or print note text in `app.py`. Counts only.
- Only `gemini_client.py` may make network calls.
- Keep the server stateless (no database, no files, no sessions).
