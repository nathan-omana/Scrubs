// Client for the Flask backend (CLAUDE.md section 10).
// NEXT_PUBLIC_USE_MOCK=1 serves everything from the in-browser mock in ./mockApi instead,
// for the public demo with no backend. Document text is only ever sent to API_URL.

import { ApiError, LOCKED_MSG } from "./errors";
import * as mock from "./mockApi";
import type { ChatResponse, Doc, Flag, NewDocument } from "./types";

// Literal process.env access so Next inlines both values at build time.
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5000").replace(/\/+$/, "");

export { ApiError } from "./errors";

type Context = "documents" | "flag" | "chat" | "other";

const NOT_FOUND_MSG = "This document is no longer on the backend. It may have restarted. Scan it again.";

// Shared fetch wrapper. Never logs request or response bodies: they contain note text.
async function request<T>(
  path: string,
  init: RequestInit = {},
  { timeoutMs = 20_000, context = "other" }: { timeoutMs?: number; context?: Context } = {},
): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: ctrl.signal });
  } catch {
    if (ctrl.signal.aborted) {
      throw new ApiError(
        "timeout",
        `The backend at ${API_URL} took longer than ${Math.round(timeoutMs / 1000)} seconds to answer. Try again.`,
      );
    }
    throw new ApiError("network", `Can't reach the backend at ${API_URL}. Check that it is running, then try again.`);
  } finally {
    clearTimeout(timer);
  }

  const raw = await res.text().catch(() => "");
  let body: any = null;
  try {
    body = raw ? JSON.parse(raw) : null;
  } catch {
    body = null; // Flask error pages are HTML.
  }

  if (res.ok) return body as T;

  const status = res.status;
  const serverMsg = [body?.error, body?.detail, body?.message].find((m) => typeof m === "string" && m.trim()) as
    | string
    | undefined;

  if (status === 403) {
    throw new ApiError("locked", context === "flag" || !serverMsg ? LOCKED_MSG : serverMsg, 403);
  }
  if (status === 404 && path.startsWith("/documents/")) {
    throw new ApiError("not_found", NOT_FOUND_MSG, 404);
  }
  if (context === "chat" && (body?.blocked === true || status === 422 || /block|leak/i.test(serverMsg ?? ""))) {
    const count = Number(body?.identifier_count ?? 1) || 1;
    throw new ApiError("blocked", serverMsg ?? "Blocked by the leak check.", status, count);
  }
  if (context === "chat" && status >= 500) {
    throw new ApiError("gemini", `Gemini could not answer. ${serverMsg ?? `The backend returned ${status}.`}`, status);
  }
  throw new ApiError("server", serverMsg ?? `Request failed (${status}).`, status);
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

// Tolerate small drift in the backend shapes. Never invents flags or values.
const FLAG_SOURCE: Record<string, Flag["source"]> = {
  presidio: "presidio",
  rules: "presidio",
  model: "model",
  gliner: "model",
  lexicon: "lexicon",
};

function normalizeFlag(f: any): Flag {
  return {
    ...f,
    reason: f.reason ?? "",
    pseudonym: f.pseudonym ?? "",
    locked: f.locked ?? f.tier === "high",
    source: FLAG_SOURCE[String(f.source ?? "").toLowerCase()] ?? "presidio",
  };
}

function normalizeDoc(d: any): Doc {
  return {
    ...d,
    title: d.title || "Untitled document",
    source: d.source === "pdf" ? "pdf" : "paste",
    original_text: d.original_text ?? d.text ?? "",
    pseudonymized_text: d.pseudonymized_text ?? null,
    status: d.status === "ready" ? "ready" : "needs_review",
    created_at: d.created_at ?? new Date().toISOString(),
    flags: ((d.flags ?? []) as any[]).map(normalizeFlag).sort((a, b) => a.start_idx - b.start_idx),
  };
}

function normalizeChat(r: any): ChatResponse {
  return {
    answer_with_pseudonyms: r?.answer_with_pseudonyms ?? "",
    outbound_text: r?.outbound_text ?? "",
    identifier_count: Number(r?.identifier_count ?? 0) || 0,
    blocked_reason: typeof r?.blocked_reason === "string" ? r.blocked_reason : undefined,
  };
}

const docPath = (id: string) => `/documents/${encodeURIComponent(id)}`;

const real = {
  // GET /documents
  async listDocuments(): Promise<Doc[]> {
    const body = await request<any>("/documents");
    const list = Array.isArray(body) ? body : (body?.documents ?? []);
    return (list as any[]).map(normalizeDoc);
  },

  // GET /documents/{id}
  async getDocument(id: string): Promise<Doc> {
    return normalizeDoc(await request<any>(docPath(id)));
  },

  // POST /documents. A backend that finds nothing returns zero flags, and we show zero flags.
  async createDocument(input: NewDocument): Promise<Doc> {
    let init: RequestInit;
    if (input.kind === "pdf") {
      const form = new FormData();
      form.append("file", input.file);
      init = { method: "POST", body: form }; // the browser sets the multipart boundary
    } else {
      init = json("POST", { title: input.title.trim() || "Pasted note", text: input.text });
    }
    return normalizeDoc(await request<any>("/documents", init, { timeoutMs: 120_000, context: "documents" }));
  },

  // PATCH /documents/{id}/flags/{flag_code}
  async setFlagMasked(id: string, flagCode: string, masked: boolean): Promise<Doc> {
    const path = `${docPath(id)}/flags/${encodeURIComponent(flagCode)}`;
    return normalizeDoc(await request<any>(path, json("PATCH", { masked }), { context: "flag" }));
  },

  // POST /documents/{id}/finalize
  async finalizeDocument(id: string): Promise<Doc> {
    return normalizeDoc(await request<any>(`${docPath(id)}/finalize`, json("POST", {})));
  },

  // GET /documents/{id}/mapping
  async getMapping(id: string): Promise<Record<string, string>> {
    const body = await request<any>(`${docPath(id)}/mapping`);
    const map = body && typeof body.mapping === "object" && body.mapping !== null ? body.mapping : (body ?? {});
    return Object.fromEntries(Object.entries(map).filter(([, v]) => typeof v === "string")) as Record<string, string>;
  },

  // POST /chat
  async chat(documentIds: string[], message: string): Promise<ChatResponse> {
    const body = await request<any>("/chat", json("POST", { document_ids: documentIds, message }), {
      timeoutMs: 90_000,
      context: "chat",
    });
    return normalizeChat(body);
  },
};

const impl = USE_MOCK ? mock : real;

export const listDocuments = () => impl.listDocuments();
export const getDocument = (id: string) => impl.getDocument(id);
export const createDocument = (input: NewDocument) => impl.createDocument(input);
export const setFlagMasked = (id: string, flagCode: string, masked: boolean) => impl.setFlagMasked(id, flagCode, masked);
export const finalizeDocument = (id: string) => impl.finalizeDocument(id);
export const getMapping = (id: string) => impl.getMapping(id);
export const chat = (documentIds: string[], message: string) => impl.chat(documentIds, message);
