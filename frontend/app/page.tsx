"use client";

import { useState } from "react";
import { SAMPLE_DOCS, entitiesOf, defaultMasked, type ScrubbedDoc } from "../lib/mockData";
import Header from "./components/Header";
import StepIndicator from "./components/StepIndicator";
import UploadStep from "./components/UploadStep";
import ReviewStep from "./components/ReviewStep";
import ChatStep from "./components/ChatStep";
import Loading from "./components/Loading";

export type Step = "upload" | "review" | "chat";

// A document the user has finished reviewing, with their masking decisions.
export type ContextDoc = {
  doc: ScrubbedDoc;
  masked: Record<string, boolean>;
  active: boolean; // included in the chat context
};

const initialMask = (doc: ScrubbedDoc) =>
  Object.fromEntries(entitiesOf(doc).map((ent) => [ent.id, defaultMasked(ent)]));

export default function Home() {
  const [step, setStep] = useState<Step>("upload");
  const [loading, setLoading] = useState<string[] | null>(null);
  const [current, setCurrent] = useState<ScrubbedDoc | null>(null);
  const [masked, setMasked] = useState<Record<string, boolean>>({});
  const [contextDocs, setContextDocs] = useState<ContextDoc[]>([]);

  // Fake a pipeline run so the loading states can be demoed.
  const runWithLoading = (messages: string[], then: () => void) => {
    setLoading(messages);
    setTimeout(() => {
      setLoading(null);
      then();
    }, 1800);
  };

  const handleUpload = (file: File | null) => {
    // Mock: cycle through the sample documents regardless of the file chosen.
    const sample = SAMPLE_DOCS[contextDocs.length % SAMPLE_DOCS.length];
    const doc = { ...sample, fileName: file?.name ?? sample.fileName };
    runWithLoading(
      ["Extracting text from PDF", "Pass 1: Presidio identifiers", "Pass 2: clinical model"],
      () => {
        setCurrent(doc);
        setMasked(initialMask(doc));
        setStep("review");
      },
    );
  };

  const handleConfirmReview = () => {
    if (!current) return;
    runWithLoading(["Generating consistent pseudonyms", "Shifting dates", "Storing mapping in vault"], () => {
      setContextDocs((docs) => [
        ...docs.filter((d) => d.doc.id !== current.id),
        { doc: current, masked, active: true },
      ]);
      setStep("chat");
    });
  };

  const goTo = (target: Step) => {
    if (target === "review" && !current) return;
    if (target === "chat" && contextDocs.length === 0) return;
    setStep(target);
  };

  return (
    <>
      <Header />
      <main className="scrubs-main">
        <div className="grid-container">
          <StepIndicator
            step={step}
            canReview={current !== null}
            canChat={contextDocs.length > 0}
            onSelect={goTo}
          />
          {loading ? (
            <Loading messages={loading} />
          ) : step === "upload" ? (
            <UploadStep
              onUpload={handleUpload}
              loadedCount={contextDocs.length}
              onSkipToChat={contextDocs.length ? () => setStep("chat") : undefined}
            />
          ) : step === "review" && current ? (
            <ReviewStep
              doc={current}
              masked={masked}
              setMasked={setMasked}
              onBack={() => setStep("upload")}
              onConfirm={handleConfirmReview}
            />
          ) : (
            <ChatStep
              contextDocs={contextDocs}
              setContextDocs={setContextDocs}
              onBack={() => setStep(current ? "review" : "upload")}
              onAddDocument={() => setStep("upload")}
              onEditDocument={(cd) => {
                setCurrent(cd.doc);
                setMasked(cd.masked);
                setStep("review");
              }}
            />
          )}
        </div>
      </main>
      <footer className="scrubs-footer">
        <div className="grid-container">
          StormHacks 2026 prototype. Synthetic data only. Only pseudonymized text is sent to Gemini.
        </div>
      </footer>
    </>
  );
}
