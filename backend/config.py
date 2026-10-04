"""
All the knobs in one place. Change behaviour here, not inside the pipeline files.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads ../.env or ./.env if present (API keys etc.)

# ---------- Gemini (the only thing that talks to the internet) ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")  # check Google's docs for the current model name
# Tried in order when the main model stays busy (503 "high demand"). Comma-separated in .env.
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.5-flash")
                          .split(",") if m.strip()]

# ---------- Presidio (layer 1: rules) ----------
# spaCy model Presidio uses for its built-in PERSON detection.
# "en_core_web_sm" = small/fast; "en_core_web_lg" = better at names but ~400 MB.
SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_sm")

# Presidio entity types we ask for. We deliberately leave out LOCATION and NRP
# (nationality/religion/politics) because they're noisy on clinical text; GLiNER handles places.
PRESIDIO_ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "DATE_TIME",
                     "PHN", "POSTAL", "FACILITY", "MRN"]

# Rename Presidio's type names to our shorter tag names.
PRESIDIO_RENAME = {"PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL", "DATE_TIME": "DATE"}

# Known BC facility names (public info, not patient data). Extend this list.
BC_FACILITIES = [
    "Vancouver General Hospital", "St. Paul's Hospital", "Lions Gate Hospital",
    "Royal Columbian Hospital", "Surrey Memorial Hospital", "Burnaby Hospital",
    "Richmond Hospital", "BC Children's Hospital", "Royal Jubilee Hospital",
    "Victoria General Hospital", "Nanaimo Regional General Hospital",
    "Kelowna General Hospital", "Royal Inland Hospital",
    "University Hospital of Northern BC", "Tofino General Hospital",
    "Bella Coola General Hospital",
]

# ---------- GLiNER (layer 2: finds names + subtle identifiers) ----------
USE_GLINER = os.getenv("USE_GLINER", "1") == "1"   # set USE_GLINER=0 to run rules only
# medium, not small: in testing, small missed 2 of 3 names and the occupation on sample_note.txt.
GLINER_MODEL = os.getenv("GLINER_MODEL", "urchade/gliner_medium-v2.1")

# Left side = plain-English label GLiNER reads. Right side = our tag type.
# GLiNER works best with simple noun phrases like these.
# Labels compete for each span, so re-check names after adding any label.
GLINER_LABELS = {
    "person name": "PERSON",
    "doctor": "PROVIDER",               # "Dr. Raj Patel": 0.95 as doctor vs 0.29 as person name
    "occupation": "OCCUPATION",
    "city or town": "LOCATION",
    "age": "AGE",
    "family member": "RELATION",        # scored relatives far higher than "family relationship"
    "employer or organization": "ORG",
    "hospital or clinic": "FACILITY",
    "street address": "ADDRESS",        # Presidio has no street-address rule, so GLiNER covers it
    "medical diagnosis or condition": "DIAGNOSIS",
    "symptom or chief complaint": "DIAGNOSIS",
    "drug or medication name": "DRUG",
    "dosage or drug dose": "DOSE",
}

# Confidence cutoff (0-1). LOWER = catches more but more false flags.
# For privacy, a miss is a leak and an extra flag is one click, so lean low. Tune on the eval set.
GLINER_THRESHOLD = float(os.getenv("GLINER_THRESHOLD", "0.3"))

# GLiNER only reads ~384 tokens at once, so we feed it chunks of roughly this many characters.
GLINER_CHUNK_CHARS = 1200

# ---------- Merge ----------
# Types found by a pattern/checksum (not a guess). When findings overlap, these types win.
# Presidio's PERSON is NOT here: it's a spaCy model guess, so GLiNER (the specialist) wins on names.
STRUCTURED_TYPES = {"PHN", "MRN", "LICENSE", "PHONE", "EMAIL", "POSTAL", "DATE", "FACILITY"}

# Words that look like names but are medical terms. Never redact these.
NEVER_REDACT = {
    "parkinson", "parkinson's", "foley", "bell", "bell's", "cushing", "cushing's",
    "crohn", "crohn's", "alzheimer", "alzheimer's", "hodgkin", "hodgkin's",
    "down", "down's", "addison", "addison's", "graves", "graves'", "huntington", "huntington's",
    # Chart words GLiNER medium sometimes flags as names or towns.
    "pt", "bc", "dob", "hx", "patient", "clinic",
}

# ---------- Tiers, labels, pseudonyms (CLAUDE.md sections 6 and 8) ----------
# Internal type -> (label the frontend shows, tier, pseudonym prefix).
# HIGH = always masked and locked. MED = masked, can unmask. LOW = kept, can mask.
TYPES = {
    "PERSON":     ("Person", "high", "PATIENT"),
    "PROVIDER":   ("Person", "high", "PROVIDER"),
    "PHN":        ("PHN", "high", "HCN"),
    "MRN":        ("MRN", "high", "MRN"),
    "LICENSE":    ("License", "high", "LICENSE"),
    "ADDRESS":    ("Address", "high", "ADDRESS"),
    "POSTAL":     ("Address", "high", "ADDRESS"),
    "PHONE":      ("Phone", "high", "PHONE"),
    "EMAIL":      ("Email", "high", "EMAIL"),
    "DATE":       ("Date", "med", "DATE"),
    "AGE":        ("Age", "med", "AGE"),
    "LOCATION":   ("Location description", "med", "LOC"),
    "FACILITY":   ("Location description", "med", "LOC"),
    "OCCUPATION": ("Unique role", "med", "ROLE"),
    "RELATION":   ("Family detail", "med", "FAMILY"),
    "ORG":        ("Employer", "med", "EMPLOYER"),
    "DESC":       ("Person description", "med", "DESC"),
    "DRUG":       ("Drug", "low", "DRUG"),
    "DOSE":       ("Dose", "low", "DOSE"),
    "DIAGNOSIS":  ("Diagnosis", "low", "DX"),
    "LAB":        ("Lab value", "low", "LAB"),
}

# Quasi-identifiers: harmless alone, identifying in combination ("74" + "Tofino" + "retired pilot").
QUASI_TYPES = {"OCCUPATION", "LOCATION", "FACILITY", "AGE", "RELATION", "ORG", "DESC"}
# How many DIFFERENT quasi kinds in one note before their reasons say "N details combined".
COMBINATION_MIN = 3

# Who the audit log records as making review decisions (no logins in this build).
CLINICIAN = os.getenv("CLINICIAN", "Dr. A. Singh")

# ---------- Upload ----------
# Port for `python app.py`. On a Mac, AirPlay Receiver also listens on 5000: 127.0.0.1:5000 still
# reaches us, but localhost:5000 may reach AirPlay. Use 127.0.0.1 in URLs, or set PORT=5001.
PORT = int(os.getenv("PORT", "5000"))

# Browser origins allowed to call the API (CORS). Comma-separated in .env.
# A trailing "/" is ignored: browsers send "http://localhost:3000", never "http://localhost:3000/".
FRONTEND_ORIGINS = {o.strip().rstrip("/") for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
                    .split(",") if o.strip()}

MAX_UPLOAD_MB = 15         # matches pipeline/pdf.py MAX_BYTES; Flask refuses bigger uploads with 413
# spaCy refuses text over 1,000,000 characters; real notes are far shorter. Fail clearly instead.
MAX_TEXT_CHARS = 200_000

# ---------- Pseudonymizing and the leak check ----------
# Masked values at least this long are also replaced wherever else they appear (any case, whole
# word), and the leak check looks for exactly those. Shorter values ("2", "Al") are only replaced
# where they were flagged: replacing every "2" would wreck the text, and checking for them would
# block every message. Both places read this one setting so they can never disagree.
MIN_REPEAT_CHARS = 3
