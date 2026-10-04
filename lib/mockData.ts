// Synthetic documents and a fake detector for the UI. Nothing here is real patient data.
// The backend replaces all of this (Presidio + our model + TiDB vault).

import type { Doc, Flag, Tier } from "./types";

type Spec = {
  text: string;
  label: string;
  tier: Tier;
  reason: string;
  source: Flag["source"];
  prefix?: string; // pseudonym prefix, e.g. "PATIENT"
  shifted?: string; // for dates: the shifted value instead of a pseudonym
};

const s = (
  text: string,
  label: string,
  tier: Tier,
  reason: string,
  source: Flag["source"],
  replace: { prefix: string } | { shifted: string },
): Spec => ({ text, label, tier, reason, source, ...replace });

const KEPT = "Clinical term, kept by default";

// CLAUDE.md section 12: the demo note and its expected flags.
export const DEMO_TITLE = "Visit note, Sept 28";
export const DEMO_NOTE =
  "Mrs. Eleanor Park, 72, MRN 4482913, was admitted on Sept 28 after a fall at her home, the small red house beside the Hope community hall. She is the retired town pharmacist, and her daughter, a nurse at Fraser Canyon Hospital, visits daily. History of atrial fibrillation. Weight 112 kg. Started on apixaban 5 mg BID. Follow up with Dr. Amrit Singh in 2 weeks.";

const DEMO_SPECS: Spec[] = [
  s("Mrs. Eleanor Park", "Person", "high", "Patient name", "presidio", { prefix: "PATIENT" }),
  s("4482913", "MRN", "high", "Medical record number", "presidio", { prefix: "MRN" }),
  s("Sept 28", "Date", "med", "Exact date", "presidio", { shifted: "Aug 13" }),
  s("the small red house beside the Hope community hall", "Location description", "med",
    "3 details combined: colour, size, landmark", "model", { prefix: "LOC" }),
  s("the retired town pharmacist", "Unique role", "med", "Only one person in a small town likely fits", "model",
    { prefix: "ROLE" }),
  s("a nurse at Fraser Canyon Hospital", "Family detail", "med", "Relative with job and workplace", "model",
    { prefix: "FAMILY" }),
  s("atrial fibrillation", "Diagnosis", "low", KEPT, "model", { prefix: "DIAGNOSIS" }),
  s("apixaban", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("5 mg BID", "Dose", "low", KEPT, "model", { prefix: "DOSE" }),
  s("Dr. Amrit Singh", "Person", "high", "Provider name", "presidio", { prefix: "PROVIDER" }),
];

const DISCHARGE_TEXT = `DISCHARGE SUMMARY

Patient: Margaret Chen    PHN: 9876 543 210    MRN: VGH-0048213
DOB: 1934-02-17    Age: 91
Address: 2231 Cedar Crescent, Hope, BC V0X 1L0
Phone: 604-555-0182

Admitted: 2026-03-28    Discharged: 2026-04-12
Attending: Dr. Rajiv Malhotra (CPSBC #31877)

Reason for admission: Community-acquired pneumonia with atrial fibrillation.

Hospital course: Patient was transferred from Fraser Canyon Hospital. Started on IV Ceftriaxone 1 g daily. Rate control with Diltiazem. Daughter Lily Chen visited daily. Patient retired from Hope Sawmill Co. in 1998.

Discharge medications:
  - Apixaban 2.5 mg PO BID
  - Amoxicillin 500 mg PO TID x 5 days

Last creatinine: 118 µmol/L
Follow-up with family physician in 2 weeks.`;

const DISCHARGE_SPECS: Spec[] = [
  s("Margaret Chen", "Person", "high", "Patient name", "presidio", { prefix: "PATIENT" }),
  s("9876 543 210", "BC PHN", "high", "BC health card number", "presidio", { prefix: "HCN" }),
  s("VGH-0048213", "MRN", "high", "Medical record number", "presidio", { prefix: "MRN" }),
  s("1934-02-17", "Date", "med", "Date of birth", "presidio", { shifted: "1933-12-03" }),
  s("91", "Age over 89", "med", "Ages over 89 are rare", "model", { prefix: "AGE" }),
  s("2231 Cedar Crescent, Hope, BC V0X 1L0", "Address", "high", "Home address", "presidio", { prefix: "ADDRESS" }),
  s("604-555-0182", "Phone", "high", "Phone number", "presidio", { prefix: "PHONE" }),
  s("2026-03-28", "Date", "med", "Exact date", "presidio", { shifted: "2026-01-11" }),
  s("2026-04-12", "Date", "med", "Exact date", "presidio", { shifted: "2026-01-26" }),
  s("Dr. Rajiv Malhotra", "Person", "high", "Provider name", "presidio", { prefix: "PROVIDER" }),
  s("31877", "Prescriber license", "high", "Prescriber license number", "presidio", { prefix: "LICENSE" }),
  s("Community-acquired pneumonia", "Diagnosis", "low", KEPT, "model", { prefix: "DIAGNOSIS" }),
  s("atrial fibrillation", "Diagnosis", "low", KEPT, "model", { prefix: "DIAGNOSIS" }),
  s("Fraser Canyon Hospital", "Location", "med", "Hospital in a small town", "model", { prefix: "LOC" }),
  s("Ceftriaxone", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("1 g", "Dose", "low", KEPT, "model", { prefix: "DOSE" }),
  s("Diltiazem", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("Lily Chen", "Person", "high", "Relative's name", "presidio", { prefix: "FAMILY" }),
  s("Hope Sawmill Co.", "Employer", "med", "Small-town employer", "model", { prefix: "EMPLOYER" }),
  s("Apixaban", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("2.5 mg", "Dose", "low", KEPT, "model", { prefix: "DOSE" }),
  s("Amoxicillin", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("500 mg", "Dose", "low", KEPT, "model", { prefix: "DOSE" }),
  s("118 µmol/L", "Lab value", "low", KEPT, "model", { prefix: "LAB" }),
];

const MEDREC_TEXT = `MEDICATION RECONCILIATION

Patient: J. Singh    PHN: 9123 456 789
Date of review: 2026-05-02
Pharmacist: Emma Tremblay

Current medications:
  - Metformin 1000 mg PO BID
  - Lisinopril 10 mg PO daily
  - Atorvastatin 40 mg PO qHS

Diagnoses: Type 2 diabetes mellitus, hypertension
Last HbA1c: 7.9%

Notes: Works night shifts at Surrey Memorial Hospital; missed evening Metformin doses. Contact at jsingh82@example.com.`;

const MEDREC_SPECS: Spec[] = [
  s("J. Singh", "Person", "high", "Patient name", "presidio", { prefix: "PATIENT" }),
  s("9123 456 789", "BC PHN", "high", "BC health card number", "presidio", { prefix: "HCN" }),
  s("2026-05-02", "Date", "med", "Exact date", "presidio", { shifted: "2026-02-14" }),
  s("Emma Tremblay", "Person", "high", "Provider name", "presidio", { prefix: "PROVIDER" }),
  s("Metformin", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("1000 mg", "Dose", "low", KEPT, "model", { prefix: "DOSE" }),
  s("Lisinopril", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("10 mg", "Dose", "low", KEPT, "model", { prefix: "DOSE" }),
  s("Atorvastatin", "Drug", "low", KEPT, "model", { prefix: "DRUG" }),
  s("40 mg", "Dose", "low", KEPT, "model", { prefix: "DOSE" }),
  s("Type 2 diabetes mellitus", "Diagnosis", "low", KEPT, "model", { prefix: "DIAGNOSIS" }),
  s("hypertension", "Diagnosis", "low", KEPT, "model", { prefix: "DIAGNOSIS" }),
  s("7.9%", "Lab value", "low", KEPT, "model", { prefix: "LAB" }),
  s("Surrey Memorial Hospital", "Employer", "med", "Workplace", "model", { prefix: "EMPLOYER" }),
  s("jsingh82@example.com", "Email", "high", "Email address", "presidio", { prefix: "EMAIL" }),
];

// Same real value gets the same pseudonym across documents (CLAUDE.md section 8).
const pseudonyms = new Map<string, string>();
const counters = new Map<string, number>();
const normalize = (v: string) => v.toLowerCase().replace(/^(mrs|mr|ms|dr)\.?\s+/, "").trim();

const pseudonymFor = (spec: Spec) => {
  if (spec.shifted) return spec.shifted;
  const key = `${spec.prefix}:${normalize(spec.text)}`;
  let p = pseudonyms.get(key);
  if (!p) {
    const n = (counters.get(spec.prefix!) ?? 0) + 1;
    counters.set(spec.prefix!, n);
    p = `[${spec.prefix}_${String(n).padStart(2, "0")}]`;
    pseudonyms.set(key, p);
  }
  return p;
};

// Number the demo note first so it gets [PATIENT_01], [LOC_01], ... as in section 12.
[...DEMO_SPECS, ...DISCHARGE_SPECS, ...MEDREC_SPECS].forEach(pseudonymFor);

const isWordChar =(c: string | undefined) => !!c && /[\p{L}\p{N}]/u.test(c);

// Finds every occurrence of every spec, longest first, skipping overlaps.
const findFlags = (text: string, specs: Spec[]): Flag[] => {
  const taken: [number, number][] = [];
  const found: Omit<Flag, "flag_code">[] = [];
  for (const spec of [...specs].sort((a, b) => b.text.length - a.text.length)) {
    let from = 0;
    for (let i = text.indexOf(spec.text, from); i !== -1; i = text.indexOf(spec.text, from)) {
      const end = i + spec.text.length;
      from = end;
      if (isWordChar(text[i - 1]) || isWordChar(text[end])) continue;
      if (taken.some(([a, b]) => i < b && end > a)) continue;
      taken.push([i, end]);
      found.push({
        start_idx: i,
        end_idx: end,
        text: spec.text,
        label: spec.label,
        tier: spec.tier,
        reason: spec.reason,
        masked: spec.tier !== "low",
        locked: spec.tier === "high",
        pseudonym: pseudonymFor(spec),
        source: spec.source,
      });
    }
  }
  return found
    .sort((a, b) => a.start_idx - b.start_idx)
    .map((f, i) => ({ ...f, flag_code: `F${i + 1}` }));
};

const ALL_SPECS = [...DEMO_SPECS, ...DISCHARGE_SPECS, ...MEDREC_SPECS].filter(
  (spec, i, all) => all.findIndex((o) => o.text === spec.text) === i,
);

// Stand-in for the detection pipeline: matches any value the mock knows about.
export const detect = (text: string) => findFlags(text, ALL_SPECS);

export const makeDoc = (
  id: string,
  title: string,
  source: Doc["source"],
  text: string,
  createdAt: Date,
  flags = detect(text),
): Doc => ({
  id,
  title,
  source,
  original_text: text,
  pseudonymized_text: null,
  status: "needs_review",
  created_at: createdAt.toISOString(),
  flags,
});

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000);

// Documents already in the workspace when the app opens.
export const seedDocs = (): Doc[] => [
  makeDoc("doc-discharge", "Discharge summary, Apr 12", "pdf", DISCHARGE_TEXT, hoursAgo(26),
    findFlags(DISCHARGE_TEXT, DISCHARGE_SPECS)),
  makeDoc("doc-medrec", "Medication reconciliation", "pdf", MEDREC_TEXT, hoursAgo(98),
    findFlags(MEDREC_TEXT, MEDREC_SPECS)),
];
