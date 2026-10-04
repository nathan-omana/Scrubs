"use client";

import { useEffect, useState } from "react";
import * as api from "../lib/api";
import { ApiError, errorText } from "../lib/errors";
import type { Doc, Flag, NewDocument } from "../lib/types";
import ChatStep, { type ChatMessage } from "./components/ChatStep";
import Loading from "./components/Loading";
import ReviewStep from "./components/ReviewStep";
import Shell, { type Notice, type Step } from "./components/Shell";
import UploadStep from "./components/UploadStep";

const SCAN_STEPS = ["Extracting text", "Pass 1: Presidio and BC rules", "Pass 2: our model", "Pass 3: BC places and roles"];
const FINALIZE_STEPS = ["Creating pseudonyms", "Shifting dates", "Keeping the mapping in memory only"];

const HEADINGS: Record<Step, [string, string]> = {
  upload: ["Add a document", "Upload a PDF or paste a note. Scrubs flags identifiers before anything goes to Gemini."],
  review: ["Review", "Check every flagged item. Masked items are replaced with pseudonyms before sending."],
  chat: ["Chat", "Gemini receives pseudonymized text only. Answers are re-identified on your screen."],
};

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function Home() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [step, setStepState] = useState<Step>("upload");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [chatIds, setChatIds] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState<{ title: string; steps: string[] } | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  const setStep = (s: Step) => {
    setNotice(null);
    setStepState(s);
  };

  const loadDocs = () => {
    setNotice(null);
    api
      .listDocuments()
      .then(setDocs)
      .catch((e) => setNotice({ text: errorText(e), retry: loadDocs }));
  };

  useEffect(loadDocs, []);

  const current = docs.find((d) => d.id === currentId) ?? null;
  const readyDocs = docs.filter((d) => d.status === "ready");

  const upsert = (doc: Doc) =>
    setDocs((ds) => (ds.some((d) => d.id === doc.id) ? ds.map((d) => (d.id === doc.id ? doc : d)) : [doc, ...ds]));

  const withLoading = async <T,>(title: string, steps: string[], work: Promise<T>) => {
    setLoading({ title, steps });
    try {
      const [result] = await Promise.all([work, wait(steps.length * 400 + 300)]);
      return result;
    } finally {
      setLoading(null);
    }
  };

  const scan = async (input: NewDocument) => {
    setScanError(null);
    setNotice(null);
    try {
      const doc = await withLoading("Scanning document", SCAN_STEPS, api.createDocument(input));
      upsert(doc);
      setCurrentId(doc.id);
      setStep("review");
    } catch (err) {
      setScanError(errorText(err, "Scanning failed."));
    }
  };

  const setMasked = async (flag: Flag, masked: boolean) => {
    if (!current) return;
    const id = current.id;
    setNotice(null);
    try {
      upsert(await api.setFlagMasked(id, flag.flag_code, masked));
    } catch (err) {
      setNotice({ text: errorText(err) });
      // Show the backend's real state after a rejected change.
      if (err instanceof ApiError && err.kind === "locked") api.getDocument(id).then(upsert).catch(() => {});
    }
  };

  const reset = async () => {
    if (!current) return;
    setNotice(null);
    try {
      for (const f of current.flags) {
        const def = f.tier !== "low";
        if (!f.locked && f.masked !== def) upsert(await api.setFlagMasked(current.id, f.flag_code, def));
      }
    } catch (err) {
      setNotice({ text: errorText(err) });
    }
  };

  const finish = async () => {
    if (!current) return;
    setNotice(null);
    try {
      const doc = await withLoading("Preparing for chat", FINALIZE_STEPS, api.finalizeDocument(current.id));
      upsert(doc);
      setChatIds((ids) => (ids.includes(doc.id) ? ids : [...ids, doc.id]));
      setStep("chat");
    } catch (err) {
      setNotice({ text: errorText(err) });
    }
  };

  const openReview = (doc: Doc) => {
    setCurrentId(doc.id);
    setStep("review");
  };

  const [title, subtitle] = HEADINGS[step];

  return (
    <Shell
      step={step}
      enabled={{ upload: true, review: current !== null, chat: readyDocs.length > 0 }}
      onSelect={setStep}
      title={title}
      subtitle={subtitle}
      alert={notice}
    >
      {loading ? (
        <Loading title={loading.title} steps={loading.steps} />
      ) : step === "review" && current ? (
        <ReviewStep doc={current} onSetMasked={setMasked} onReset={reset} onDone={finish} />
      ) : step === "chat" ? (
        <ChatStep
          readyDocs={readyDocs}
          selectedIds={chatIds}
          setSelectedIds={setChatIds}
          messages={messages}
          setMessages={setMessages}
          onAddDocument={() => setStep("upload")}
          onReview={openReview}
        />
      ) : (
        <UploadStep docs={docs} onScan={scan} onOpen={openReview} error={scanError} />
      )}
    </Shell>
  );
}
