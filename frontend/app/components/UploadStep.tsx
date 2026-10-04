"use client";

import { useRef, useState } from "react";

type Props = {
  onUpload: (file: File | null) => void;
  loadedCount: number;
  onSkipToChat?: () => void;
};

export default function UploadStep({ onUpload, loadedCount, onSkipToChat }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);

  const pick = (f: File | undefined) => {
    if (f && f.type === "application/pdf") setFile(f);
  };

  return (
    <div className="grid-row grid-gap-lg">
      <section className="grid-col-12 tablet-lg:grid-col-8">
        <div className="scrubs-panel">
          <h1 className="scrubs-h1">Upload a patient document</h1>
          <p className="scrubs-lead">
            Scrubs finds names, health card numbers, dates and other identifiers, replaces them with pseudonyms, and only
            then lets you ask Gemini about the document.
          </p>

          <div
            className={`scrubs-dropzone ${dragging ? "is-dragging" : ""}`}
            onDragOver={(ev) => {
              ev.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(ev) => {
              ev.preventDefault();
              setDragging(false);
              pick(ev.dataTransfer.files[0]);
            }}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf"
              hidden
              onChange={(ev) => pick(ev.target.files?.[0])}
            />
            {file ? (
              <>
                <div className="scrubs-file-chip">
                  <span className="scrubs-file-chip__type">PDF</span>
                  <span className="scrubs-mono">{file.name}</span>
                  <span className="text-base">{(file.size / 1024).toFixed(0)} KB</span>
                </div>
                <div className="margin-top-1 text-base">Click to choose a different file</div>
              </>
            ) : (
              <>
                <div className="scrubs-dropzone__title">Drag a PDF here or choose a file</div>
                <div className="text-base">Text-based PDFs only. Scanned documents are not supported yet.</div>
              </>
            )}
          </div>

          <div className="margin-top-3 display-flex flex-align-center flex-wrap">
            <button type="button" className="usa-button" disabled={!file} onClick={() => onUpload(file)}>
              Scan document
            </button>
            <button type="button" className="usa-button usa-button--unstyled margin-left-2" onClick={() => onUpload(null)}>
              Use a synthetic sample instead
            </button>
            {onSkipToChat && (
              <button type="button" className="usa-button usa-button--outline margin-left-auto" onClick={onSkipToChat}>
                Back to chat ({loadedCount} loaded)
              </button>
            )}
          </div>
        </div>
      </section>

      <aside className="grid-col-12 tablet-lg:grid-col-4">
        <div className="scrubs-panel scrubs-panel--sidebar">
          <h2 className="scrubs-h3">What happens to your file</h2>
          <ol className="scrubs-steps-list">
            <li>Text is extracted on our server. The PDF is not stored.</li>
            <li>
              <strong>Presidio</strong> flags standard identifiers.
            </li>
            <li>
              <strong>Our model</strong> catches what Presidio missed and keeps drug names, doses and diagnoses.
            </li>
            <li>You review every flagged item before anything leaves.</li>
            <li>Gemini only receives the pseudonymized text.</li>
          </ol>
          <h2 className="scrubs-h3 margin-top-3">Risk levels</h2>
          <dl className="scrubs-legend">
            <dt>
              <span className="scrubs-tag scrubs-tag--high">HIGH</span>
            </dt>
            <dd>Always masked. Names, health card numbers, MRNs, addresses, phones.</dd>
            <dt>
              <span className="scrubs-tag scrubs-tag--medium">MED</span>
            </dt>
            <dd>Masked by default. Exact dates, ages over 89, small towns, employers.</dd>
            <dt>
              <span className="scrubs-tag scrubs-tag--low">LOW</span>
            </dt>
            <dd>Kept by default. Drugs, doses, diagnoses, lab values.</dd>
          </dl>
        </div>
      </aside>
    </div>
  );
}
