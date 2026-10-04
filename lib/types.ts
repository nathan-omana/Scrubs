// Shapes mirror the FastAPI responses in CLAUDE.md section 10.

export type Tier = "high" | "med" | "low";

export type Flag = {
  flag_code: string; // "F1"
  start_idx: number;
  end_idx: number;
  text: string;
  label: string; // "Location description"
  tier: Tier;
  reason: string;
  masked: boolean;
  locked: boolean;
  // What replaces the text when masked: "[LOC_01]", or a shifted date.
  pseudonym: string;
  // Which pass found it. Shown in Review so the demo can point at our model.
  source: "presidio" | "model";
};

export type Doc = {
  id: string;
  title: string;
  source: "pdf" | "paste";
  original_text: string;
  pseudonymized_text: string | null;
  status: "needs_review" | "ready";
  created_at: string;
  flags: Flag[];
};

export type ChatResponse = {
  answer_with_pseudonyms: string;
  outbound_text: string;
  identifier_count: number;
};

export type NewDocument = { kind: "pdf"; file: File } | { kind: "paste"; title: string; text: string };
