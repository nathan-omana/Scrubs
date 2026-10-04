# Scrubs

Scrubs lets clinicians use an AI chatbot on patient documents without the chatbot ever seeing who the patient is.

You upload a PDF or paste a note. Scrubs finds the identifiers (names, health card numbers, dates, addresses, and indirect details like "the retired town pharmacist"), lets you review each one, and replaces the masked ones with consistent pseudonyms such as `[PATIENT_01]`. Only that pseudonymized text is sent to the chatbot (Google Gemini). The answer is turned back into real names on your screen.

Built at StormHacks 2026 by Armin, Felix, Krish and Nathan. **Synthetic data only:** every document in this repo is made up.

## How it works

1. **Upload** a text-based PDF or paste a note.
2. **Detect.** Presidio with BC-specific rules (PHN check digit, postal codes, MRNs, prescriber numbers), GLiNER for indirect identifiers, and a list of BC towns, facilities and roles.
3. **Review.** Each item is tagged HIGH (always masked), MED (masked by default) or LOW (drugs, doses, diagnoses: kept by default). Click any item to mask or keep it.
4. **Chat.** Ask for a referral letter, discharge summary or handoff note. The chatbot only receives pseudonyms. Dates are shifted by one offset per patient, so intervals stay correct.

Documents, flags and the pseudonym mapping live only in memory. Nothing is written to disk or a database, and everything is cleared on restart.

## Install the desktop app (Windows)

1. Download `Scrubs-0.1.0.msi` from the [Releases page](../../releases). It is about 930 MB.
2. Double-click it. Windows shows "Windows protected your PC" because the installer isn't code-signed: click **More info**, then **Run anyway**.
3. Follow the wizard and choose an install folder (default `C:\Program Files\Scrubs`).
4. Open Scrubs. The first time, it asks for your Gemini API key. The key is stored in Windows Credential Manager on your computer. Leave it blank to use Scrubs without the chatbot.
5. The window shows "Starting Scrubs" while the detection models load (up to a minute), then the app appears.

Detection runs entirely on your computer. The only thing sent over the internet is the pseudonymized text you choose to send to the chatbot.

To change the key later, open **Credential Manager → Windows Credentials**, remove the **Scrubs** entry, and restart Scrubs. To uninstall, use **Settings → Apps**.

## Run it for development

Backend (Python 3.11):

```
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\pip install -r requirements.txt
backend\.venv\Scripts\python -m spacy download en_core_web_sm
copy .env.example .env        (then add your GEMINI_API_KEY)
cd backend
.venv\Scripts\python app.py   (http://127.0.0.1:5000)
```

Frontend, in a second terminal from the repo root:

```
npm install
npm run dev                   (http://localhost:3000)
```

Set `NEXT_PUBLIC_USE_MOCK=1` in `.env` to run the frontend on sample data with no backend.

## Repo layout

| Path | What |
|---|---|
| `app/`, `lib/` | Next.js frontend |
| `backend/` | Flask API and the detection pipeline (`backend/pipeline/`) |
| `desktop/` | Windows desktop app and MSI build ([desktop/README.md](desktop/README.md)) |
| `eval/` | Synthetic test notes and `eval/run.py`, which compares default Presidio with our pipeline ([eval/README.md](eval/README.md)) |
| `data/` | BC lexicon and synthetic sample PDFs |
| `CLAUDE.md` | Full project spec |

## Sponsor tracks

- **Gemini API:** the chatbot over pseudonymized text.
- **TiDB:** the public BC lexicon (towns, facilities, identifying roles), downloaded read-only and matched locally.
- **Snowflake:** audit log of mask and unmask decisions, counts only, never text.

## Limits

This is a hackathon prototype. It has not been validated for clinical use. Always review the flagged items before sending anything.
