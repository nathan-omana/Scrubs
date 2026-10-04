# TiDB Setup: BC Lexicon (handoff for P2)

You're setting up and populating the TiDB database. **The code is already written and tested.** Your job is the cloud setup, loading the data, proving it works, and owning the lexicon from here on.

Read `PROJECT_CONTEXT.md` first (especially section 4, the hard rules).

---

## 1. What TiDB does in Scrub In (in one minute)

GLiNER (our phrase-labeling model) is good with context but **scores some identifiers low**. In testing, "bush pilot" scored 0.31 and nearly slipped through. So we keep a **curated list of known BC identifiers**: towns, hospitals and identifying occupations. That's the **lexicon**.

```
TiDB Cloud (PUBLIC data only)                 Scrub In gateway (hospital / laptop)
─────────────────────────────                 ────────────────────────────────────
bc_lexicon table  ──── one read-only SELECT ──→ held in memory
  "Tofino"      LOCATION                        every note is matched LOCALLY
  "bush pilot"  OCCUPATION                      against the list
  "Hope"        LOCATION (ambiguous)
                                 ✗ nothing ever goes back up
```

- **Data only flows DOWN.** The gateway never sends note text to TiDB.
- **The gateway logs in as a read-only user,** so it *can't* write to TiDB even if someone tried. "Nothing goes up" is enforced by the database itself.
- **If TiDB is unreachable,** the gateway uses `data/lexicon_seed.csv` from the repo. The demo never depends on Wi-Fi.
- **Ambiguous entries** (Hope, Golden, Nelson, judge...) are also everyday words or names, so they only count when GLiNER flagged the same spot too.

**Pitch line for the TiDB judge:** *"TiDB is our update channel: hospitals pull BC rules down, nothing goes up, and the database enforces it."*

---

## 2. What's already built

| File | What it does |
|---|---|
| `data/lexicon_seed.csv` | 328 public entries: 182 BC communities, 44 BC facilities, 102 identifying occupations. 40 are marked ambiguous. |
| `scripts/seed_lexicon.py` | Creates the `bc_lexicon` table and upserts the CSV (uses the **admin** login) |
| `scripts/verify_lexicon.py` | Proves (1) the gateway can read and (2) the gateway **cannot write** |
| `backend/pipeline/lexicon.py` | The server's loader: one SELECT over TLS, CSV fallback, local whole-word matching |
| `backend/pipeline/merge.py` | Combines lexicon hits with the other detectors (ambiguous entries need GLiNER's agreement) |
| `backend/tests/test_lexicon.py` | Tests with a fake TiDB: all pass |
| `GET /health` | Now reports `"lexicon": "tidb" \| "csv" \| "off"` |

---

## 3. Your steps (about 30–45 minutes)

### Step 1: Create the cluster (web, about 10 min)

1. Sign up at **tidbcloud.com** and create a **Starter** (free) cluster.
2. Open the cluster's **SQL Editor** (or connect with any MySQL client) and run:
   ```sql
   CREATE DATABASE IF NOT EXISTS scrubin;
   ```
3. Click **Connect** and note the **host**, **port (4000)** and your **root username**.
   On Starter, usernames have a **prefix**, like `2aBcDeF.root`. Write the prefix down, because new users need it too.

### Step 2: Create the two users

In the SQL editor, replacing `PREFIX` with your prefix and choosing strong passwords:

```sql
-- Admin user: only the seed script uses it
CREATE USER 'PREFIX.seeder'@'%' IDENTIFIED BY '<strong password 1>';
GRANT ALL PRIVILEGES ON scrubin.* TO 'PREFIX.seeder'@'%';

-- Gateway user: READ-ONLY, used by every running gateway
CREATE USER 'PREFIX.gateway'@'%' IDENTIFIED BY '<strong password 2>';
GRANT SELECT ON scrubin.* TO 'PREFIX.gateway'@'%';
```

(You can use the root user as the admin instead, but a separate seeder user is cleaner.)

### Step 3: Put credentials in `.env` (never in the repo, never in a chat)

In the repo root `.env` (copy from `.env.example` if needed):

```
LEXICON_SOURCE=auto
TIDB_HOST=<host from the Connect dialog>
TIDB_PORT=4000
TIDB_DATABASE=scrubin
TIDB_USER=PREFIX.gateway
TIDB_PASSWORD=<password 2>
TIDB_ADMIN_USER=PREFIX.seeder
TIDB_ADMIN_PASSWORD=<password 1>
```

Teammates only need the **gateway** values. Share those privately (a DM or password manager). Only you need the admin values.

### Step 4: Install the client libraries

```bash
source .venv/bin/activate
pip install -r requirements.txt        # adds pymysql + certifi
```

### Step 5: Load the data

```bash
python scripts/seed_lexicon.py --dry-run   # checks the CSV, touches nothing
python scripts/seed_lexicon.py             # creates the table + loads 328 rows
```

Expected: `TiDB now has: {'FACILITY': 44, 'LOCATION': 182, 'OCCUPATION': 102}`

### Step 6: Prove it works

```bash
python scripts/verify_lexicon.py
```

Expected:

```
1. READ  ok: gateway user can see 328 lexicon rows
2. WRITE blocked as expected: ... INSERT command denied ...
3. lexicon.load() used source: tidb
```

**Screenshot this output for the TiDB judges and the Devpost write-up.**

### Step 7: See it in the pipeline

```bash
cd backend
python -m tests.test_lexicon
python demo.py sample_note.txt             # look for found_by "lexicon" in the table
```

---

## 4. Owning the lexicon from here

**To add or change entries:** edit `data/lexicon_seed.csv` (columns `phrase,type,ambiguous`), then re-run `python scripts/seed_lexicon.py`. It upserts, so existing rows get their `ambiguous` flag updated and their `version` bumped.

**Rules for entries:**

- **Public information only:** place names, facility names, job titles. **Never** a patient's name or anything from a note.
- `type` must be `LOCATION`, `FACILITY` or `OCCUPATION`.
- Set `ambiguous=1` if the phrase is also a common word or a person's name (Hope, Golden, Trail, Nelson, Oliver, Taylor, judge, miner...). Otherwise "I hope she improves" would get flagged.
- **Matching is case-sensitive and whole-word.** "Tofino" matches, "tofino" doesn't. Add lowercase variants only if notes really write them that way.
- **Don't add clinical roles** (nurse, RN, physician). Those usually describe the care team, not the patient.

**Good additions to research:**

- More small and remote BC communities, especially First Nations communities and coastal or northern towns. These are the highest re-identification risk.
- More BC facilities (health centres, long-term care homes).
- More rare or identifying occupations (whatever's unusual in a small town).

---

## 5. Optional, after everything above works: vector search to expand the lexicon

This deepens the TiDB integration for the prize. It's **offline, on public data only**.

**Idea:** load a big public pool of phrases (e.g. all of Canada's official occupation titles and BC place names) into TiDB, each with an **embedding** (a list of numbers representing its meaning). Then ask TiDB which pool phrases are **closest in meaning** to the risky ones we already have:

```sql
CREATE TABLE occupation_pool (
  phrase VARCHAR(120),
  embedding VECTOR(768)          -- size depends on the embedding model
);

SELECT phrase, VEC_COSINE_DISTANCE(embedding, :bush_pilot_vector) AS distance
FROM occupation_pool
ORDER BY distance
LIMIT 10;
-- → floatplane pilot, charter pilot, heli-logger, ...
```

A person reviews the suggestions and adds the good ones to `lexicon_seed.csv`. Embeddings can come from TiDB's built-in embedding feature (check whether your cluster has it) or from Gemini's embedding API. **These are public phrases only.**

Build this as `scripts/expand_lexicon.py`. It's never run by the server.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `Access denied for user` | Missing the username **prefix** (`PREFIX.gateway`), or the wrong password |
| SSL / certificate errors | Make sure `certifi` is installed. The code already uses TLS with certificate checks. |
| Connection timeout | Check the cluster is running and its public endpoint is enabled in TiDB Cloud's networking settings |
| `/health` says `"lexicon": "csv"` | TiDB failed, so it fell back. The server log says why (error type only, never data). |
| Verify step 2 says WRITE ALLOWED | The gateway user has too many grants. Run `REVOKE ALL PRIVILEGES ON scrubin.* FROM 'PREFIX.gateway'@'%'; GRANT SELECT ON scrubin.* TO 'PREFIX.gateway'@'%';` |

---

## 7. Starter prompt for your Claude Code session

> Read PROJECT_CONTEXT.md and TIDB_SETUP.md. I've created the TiDB Cloud cluster and filled in the TIDB_* values in .env myself (don't print them). Run seed_lexicon.py --dry-run, then seed_lexicon.py, then verify_lexicon.py, then `python -m tests.test_lexicon` and `python demo.py sample_note.txt` from backend/. Show me the outputs. Then help me research and add 50+ more small or remote BC communities and identifying occupations to data/lexicon_seed.csv, with correct ambiguous flags. Public information only. Re-seed and re-verify. Never send note text to TiDB; never store patient data there.
