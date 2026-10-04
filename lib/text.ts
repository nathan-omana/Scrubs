import type { Doc, Flag } from "./types";

export type Segment = string | Flag;

// Original text split into plain chunks and flagged spans, in order.
export const segmentsOf = (doc: Doc): Segment[] => {
  const out: Segment[] = [];
  let pos = 0;
  for (const f of doc.flags) {
    if (f.start_idx > pos) out.push(doc.original_text.slice(pos, f.start_idx));
    out.push(f);
    pos = f.end_idx;
  }
  if (pos < doc.original_text.length) out.push(doc.original_text.slice(pos));
  return out;
};

// What Gemini receives for this flag.
export const sentValue = (f: Flag) => (f.masked ? f.pseudonym : f.text);

export const pseudonymize = (doc: Doc) =>
  segmentsOf(doc)
    .map((seg) => (typeof seg === "string" ? seg : sentValue(seg)))
    .join("");

// Pseudonym (or shifted date) to real value, for masked flags only.
export const mappingOf = (doc: Doc): Record<string, string> =>
  Object.fromEntries(doc.flags.filter((f) => f.masked).map((f) => [f.pseudonym, f.text]));

export const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export type Part = { text: string; key?: string };

// Splits text on any of the given keys. Unknown or altered pseudonyms are left as plain text.
export const splitOn = (text: string, keys: string[]): Part[] => {
  if (keys.length === 0) return [{ text }];
  const re = new RegExp(`(${[...keys].sort((a, b) => b.length - a.length).map(escape).join("|")})`, "g");
  return text
    .split(re)
    .filter(Boolean)
    .map((t) => (keys.includes(t) ? { text: t, key: t } : { text: t }));
};

export const replaceAll = (text: string, pairs: [string, string][]) =>
  [...pairs]
    .sort((a, b) => b[0].length - a[0].length)
    .reduce((t, [from, to]) => t.split(from).join(to), text);

export const wordCount = (text: string) => text.split(/\s+/).filter(Boolean).length;

// True if value appears in text as a whole word or phrase, ignoring case.
export const containsTerm = (text: string, value: string) =>
  new RegExp(`(?<![\\p{L}\\p{N}])${escape(value)}(?![\\p{L}\\p{N}])`, "iu").test(text);
