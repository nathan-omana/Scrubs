// Mock data for the UI mockup. Everything here is synthetic.
// Shape mirrors what the backend should eventually return from /analyze.

export type Risk = "HIGH" | "MEDIUM" | "LOW";

export type Entity = {
  id: string;
  text: string;
  type: string; // e.g. PERSON, HEALTH_CARD, DRUG
  risk: Risk;
  pseudonym: string;
  source: "Presidio" | "Model" | "Both";
  confidence: number;
};

// A document is a list of plain-text chunks and detected entities, in order.
export type Segment = string | Entity;

export type ScrubbedDoc = {
  id: string;
  fileName: string;
  title: string;
  pages: number;
  segments: Segment[];
};

const e = (
  id: string,
  text: string,
  type: string,
  risk: Risk,
  pseudonym: string,
  source: Entity["source"] = "Presidio",
  confidence = 0.95,
): Entity => ({ id, text, type, risk, pseudonym, source, confidence });

const dischargeSummary: ScrubbedDoc = {
  id: "doc-1",
  fileName: "discharge_summary_0412.pdf",
  title: "Discharge Summary",
  pages: 2,
  segments: [
    "DISCHARGE SUMMARY\n\nPatient: ",
    e("d1-1", "Margaret Chen", "PERSON", "HIGH", "[PATIENT_01]", "Both", 0.99),
    "    PHN: ",
    e("d1-2", "9876 543 210", "BC_HEALTH_CARD", "HIGH", "[HCN_01]", "Presidio", 0.98),
    "    MRN: ",
    e("d1-3", "VGH-0048213", "MRN", "HIGH", "[MRN_01]", "Model", 0.91),
    "\nDOB: ",
    e("d1-4", "1934-02-17", "DATE_OF_BIRTH", "HIGH", "[DOB_01]", "Presidio", 0.97),
    "    Age: ",
    e("d1-5", "91", "AGE_OVER_89", "MEDIUM", "[AGE_90+]", "Model", 0.88),
    "\nAddress: ",
    e("d1-6", "2231 Cedar Crescent, Hope, BC V0X 1L0", "ADDRESS", "HIGH", "[ADDRESS_01]", "Both", 0.96),
    "\nPhone: ",
    e("d1-7", "604-555-0182", "PHONE", "HIGH", "[PHONE_01]", "Presidio", 0.99),
    "\n\nAdmitted: ",
    e("d1-8", "2026-03-28", "DATE", "MEDIUM", "2026-01-11", "Presidio", 0.93),
    "    Discharged: ",
    e("d1-9", "2026-04-12", "DATE", "MEDIUM", "2026-01-26", "Presidio", 0.93),
    "\nAttending: Dr. ",
    e("d1-10", "Rajiv Malhotra", "PERSON", "HIGH", "[CLINICIAN_01]", "Presidio", 0.97),
    " (CPSBC #",
    e("d1-11", "31877", "PRESCRIBER_ID", "HIGH", "[LICENSE_01]", "Model", 0.86),
    ")\n\nReason for admission: ",
    e("d1-12", "Community-acquired pneumonia", "DIAGNOSIS", "LOW", "[DIAGNOSIS_01]", "Model", 0.94),
    " with ",
    e("d1-13", "atrial fibrillation", "DIAGNOSIS", "LOW", "[DIAGNOSIS_02]", "Model", 0.92),
    ".\n\nHospital course: Patient was transferred from ",
    e("d1-14", "Fraser Canyon Hospital", "FACILITY", "MEDIUM", "[FACILITY_01]", "Model", 0.84),
    " in a small rural community. Started on IV ",
    e("d1-15", "Ceftriaxone", "DRUG", "LOW", "[DRUG_01]", "Model", 0.97),
    " ",
    e("d1-16", "1 g", "DOSE", "LOW", "[DOSE_01]", "Model", 0.9),
    " daily. Rate control with ",
    e("d1-17", "Diltiazem", "DRUG", "LOW", "[DRUG_02]", "Model", 0.95),
    ". Daughter ",
    e("d1-18", "Lily Chen", "PERSON", "HIGH", "[CONTACT_01]", "Both", 0.97),
    " visited daily. Patient retired from ",
    e("d1-19", "Hope Sawmill Co.", "EMPLOYER", "MEDIUM", "[EMPLOYER_01]", "Model", 0.79),
    " in 1998.\n\nDischarge medications:\n  - ",
    e("d1-20", "Apixaban", "DRUG", "LOW", "[DRUG_03]", "Model", 0.96),
    " ",
    e("d1-21", "2.5 mg", "DOSE", "LOW", "[DOSE_02]", "Model", 0.93),
    " PO BID\n  - ",
    e("d1-22", "Amoxicillin", "DRUG", "LOW", "[DRUG_04]", "Model", 0.97),
    " ",
    e("d1-23", "500 mg", "DOSE", "LOW", "[DOSE_03]", "Model", 0.93),
    " PO TID x 5 days\n\nLast creatinine: ",
    e("d1-24", "118 µmol/L", "LAB_VALUE", "LOW", "[LAB_01]", "Model", 0.89),
    "\nFollow-up with family physician in 2 weeks.",
  ],
};

const medicationReview: ScrubbedDoc = {
  id: "doc-2",
  fileName: "med_reconciliation_JS.pdf",
  title: "Medication Reconciliation",
  pages: 1,
  segments: [
    "MEDICATION RECONCILIATION\n\nPatient: ",
    e("d2-1", "J. Singh", "PERSON", "HIGH", "[PATIENT_02]", "Both", 0.97),
    "    PHN: ",
    e("d2-2", "9123 456 789", "BC_HEALTH_CARD", "HIGH", "[HCN_02]", "Presidio", 0.98),
    "\nDate of review: ",
    e("d2-3", "2026-05-02", "DATE", "MEDIUM", "2026-02-14", "Presidio", 0.94),
    "\nPharmacist: ",
    e("d2-4", "Emma Tremblay", "PERSON", "HIGH", "[CLINICIAN_02]", "Presidio", 0.96),
    "\n\nCurrent medications:\n  - ",
    e("d2-5", "Metformin", "DRUG", "LOW", "[DRUG_05]", "Model", 0.97),
    " ",
    e("d2-6", "1000 mg", "DOSE", "LOW", "[DOSE_04]", "Model", 0.92),
    " PO BID\n  - ",
    e("d2-7", "Lisinopril", "DRUG", "LOW", "[DRUG_06]", "Model", 0.96),
    " ",
    e("d2-8", "10 mg", "DOSE", "LOW", "[DOSE_05]", "Model", 0.92),
    " PO daily\n  - ",
    e("d2-9", "Atorvastatin", "DRUG", "LOW", "[DRUG_07]", "Model", 0.96),
    " ",
    e("d2-10", "40 mg", "DOSE", "LOW", "[DOSE_06]", "Model", 0.92),
    " PO qHS\n\nDiagnoses: ",
    e("d2-11", "Type 2 diabetes mellitus", "DIAGNOSIS", "LOW", "[DIAGNOSIS_03]", "Model", 0.95),
    ", ",
    e("d2-12", "hypertension", "DIAGNOSIS", "LOW", "[DIAGNOSIS_04]", "Model", 0.94),
    "\nLast HbA1c: ",
    e("d2-13", "7.9%", "LAB_VALUE", "LOW", "[LAB_02]", "Model", 0.9),
    "\n\nNotes: Works night shifts at ",
    e("d2-14", "Surrey Memorial Hospital", "EMPLOYER", "MEDIUM", "[EMPLOYER_02]", "Model", 0.81),
    "; missed evening Metformin doses. Contact at ",
    e("d2-15", "jsingh82@example.com", "EMAIL", "HIGH", "[EMAIL_01]", "Presidio", 0.99),
    ".",
  ],
};

export const SAMPLE_DOCS = [dischargeSummary, medicationReview];

export const entitiesOf = (doc: ScrubbedDoc) =>
  doc.segments.filter((s): s is Entity => typeof s !== "string");

// Default masking decision per risk level.
export const defaultMasked = (ent: Entity) => ent.risk !== "LOW";

// Canned Gemini replies for the mockup. Written in pseudonymized form,
// exactly as Gemini would return them; the UI re-identifies them.
export const CANNED_REPLIES: string[] = [
  "[PATIENT_01] was admitted for [DIAGNOSIS_01] with [DIAGNOSIS_02]. Discharge medications are [DRUG_03] [DOSE_02] PO BID for anticoagulation and [DRUG_04] [DOSE_03] PO TID for 5 days to complete the antibiotic course.\n\nGiven an age of [AGE_90+] and a creatinine of [LAB_01], confirm the [DRUG_03] dose-reduction criteria are met before discharge.",
  "No direct interaction between [DRUG_03] and [DRUG_04] is expected. [DRUG_02] was used for rate control in hospital but is not on the discharge list; consider confirming with [CLINICIAN_01] whether that was intended.",
  "Across the loaded documents, [PATIENT_02] is on [DRUG_05], [DRUG_06] and [DRUG_07]. The HbA1c of [LAB_02] and missed evening doses suggest an adherence issue related to shift work rather than treatment failure.",
];
