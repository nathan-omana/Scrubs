# How This Was Built: Process and Decisions

This explains **how** I approached the build, the choices I made and why, the problems I found and fixed while testing, and what I chose to leave out.

---

## 1. Starting point

The agreed stack from our discussion:

- **Layer 1:** Presidio, used only to *find*, never to replace
- **Layer 2:** GLiNER (not Ollama), a phrase labeler, not a chatbot
- **Merge → risk rules → clinician review → tag → Gemini → restore**
- **No storage:** stateless server, no database, nothing written to disk, logs hold counts only
- **Don't over-engineer:** the smallest thing that works end to end, with comments explaining each part

---

## 2. Order of work

1. **Checked facts before writing code.**
   - **The BC PHN check digit.** I didn't want to guess the weights. I confirmed them against the BC MSP "PHN check digit routine" and its worked example (`9123947241` → valid), and that example is now a test.
   - **The GLiNER API.** I read the library's source to confirm `predict_entities(text, labels, threshold)` and its output fields (`start`, `end`, `label`, `score`), plus `from_pretrained`'s options.
   - **How Flask handles uploads.** I read Werkzeug's code and confirmed it writes uploads over 500 KB to a **temp file on disk**. That breaks "never stored", so I overrode it.
2. **Wrote one file per pipeline step,** each with a single job, so the team can work on them separately.
3. **Built a terminal demo before the server,** so the pipeline can be seen working without any frontend.
4. **Tested in a sandbox** with fake GLiNER and fake Gemini. The real model and API weren't reachable there.
5. **Fixed what testing found** (section 4).
6. **Wrote these docs.**

---

## 3. Key decisions and why

| Decision | Why |
|---|---|
| **Presidio finds but doesn't replace** | If Presidio replaced text first, GLiNER couldn't see or fix its mistakes ("Foley" tagged as a person). Replacement happens once, at the end, after review. |
| **GLiNER sees the raw note** | Everything is local, so there's no privacy cost, and the model gets full context. |
| **Keep every finding from both layers** | A missed identifier is a leak. An extra flag costs the clinician one click. |
| **Structured rules win type conflicts** | A PHN that passes its checksum is more trustworthy than any model's guess. |
| **GLiNER beats Presidio's spaCy on names** | spaCy's small model learned from general web text and makes odd guesses on clinical text. GLiNER is the specialist. |
| **Risk comes from rules, not a model** | Explainable ("town + age + occupation = RED") and the same answer every time. Judges and privacy officers can check it. |
| **Server holds nothing between requests** | The mapping goes back to the browser, and chat history comes in with each request. "Not stored" is true by design, not by cleanup. |
| **One file talks to the internet** | `gemini_client.py`. Easy to audit, and easy to point at in a demo. |
| **`demo.py` + smoke tests** | Lets anyone on the team check the pipeline in 10 seconds without the frontend. |
| **Settings in `config.py`** | Tuning (labels, threshold, lists) shouldn't require touching logic. |
| **spaCy small model by default** | Fast to install. GLiNER handles names anyway. Switching to `en_core_web_lg` is one setting. |

---

## 4. Problems found while testing, and the fixes

Each of these came from running the sample note through the pipeline. They show why testing on a realistic note matters.

1. **A hidden network call in Presidio.**
   - **Problem:** Presidio's email checker uses a library (`tldextract`) that **tried to download a domain list from publicsuffix.org** the first time it ran. No patient data was sent, but it broke our "no network during detection" promise.
   - **Fix:** that library is now forced to use its built-in copy (`rules.py`, top of file).
   - **Lesson:** run with the network off before claiming "offline."
2. **Durations tagged as dates.**
   - **Problem:** Presidio tagged "day 5" as a date, which removes clinically useful information (your pitch says intervals are kept).
   - **Fix:** a filter drops durations ("7 days", "3 weeks") and relative days ("day 5", "POD 2").
3. **spaCy false positives on names.**
   - **Problem:** spaCy tagged "bush" (from "retired bush pilot") and "Daughter Claire" as PERSON.
   - **Fixes:**
     - In type conflicts, GLiNER now beats spaCy's PERSON guess.
     - If GLiNER already covers every word of a spaCy PERSON span with more precise spans ("Daughter" = RELATION, "Claire" = PERSON), the spaCy span is dropped.
     - If GLiNER missed any word, the spaCy span is **kept**, so no leak.
4. **Repeated values only partly tagged.**
   - **Problem:** if a detector finds "Tofino" once but misses a second mention, the second one would go to Gemini.
   - **Fix:** tagging now replaces **every** occurrence of an approved value.
5. **Uploads written to disk.**
   - **Problem:** Werkzeug wrote large uploads to a temp file by default.
   - **Fix:** a custom request class keeps uploads in memory, and a test checks it.
6. **Huge documents crashed spaCy** (its limit is 1,000,000 characters).
   - **Fix:** a clear "too long" error at 200,000 characters.
7. **Presidio's own logs.** They were noisy at INFO level, and debug logs could include text, so they're set to errors only.

---

## 5. What I deliberately didn't build

Following "don't over-engineer yet":

- **Date shifting.** Dates are just tagged for now. It's the next feature to add.
- **GLiNER fine-tuning and training scripts.** Measure the untrained model on the eval set first, then fine-tune only if specific labels are weak.
- **The evaluation script** (Presidio vs. Presidio + GLiNER). That's Person 4's job, and it shouldn't be written by whoever built the detector.
- **OCR, logins, Docker, deployment,** and an optional Gemini "re-identification check" before sending.
- **A test framework.** One plain smoke-test file is enough for now.

---

## 6. Known limitations to be honest about

- **The real GLiNER hasn't run yet.** The tests use a fake model with perfect answers, so real results will be worse, possibly much worse on clinical shorthand. **Run `demo.py` first and look at what it misses.**
- **The never-redact list is short.** It will need additions as you find more medical eponyms.
- **The risk rule is simple** (3+ kinds of quasi-identifiers = RED). Tune it on real-style notes.
- **The last-resort check only catches raw PHNs and emails.** It's a safety net, not the main protection.
- **No detector catches 100%.** The honest claim is "the raw document never leaves the device, and only reviewed, de-identified text reaches the AI," backed by your recall numbers.

---

## 7. Suggested next steps (in order)

1. Run `demo.py` with the **real** GLiNER on `sample_note.txt` and 3–4 more notes. Write down misses and false flags.
2. Tune `GLINER_LABELS` wording and `GLINER_THRESHOLD`.
3. Connect the frontend: `/analyze` → review → `/tag` → `/chat`, and port `restore()` to JS.
4. Person 4 builds the eval script and hand-labeled notes.
5. Add date shifting.
6. Fine-tune GLiNER only if the eval shows specific weak labels.
