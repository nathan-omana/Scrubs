"use client";

import { useEffect, useRef, useState } from "react";
import { DEMO_NOTE, DEMO_TITLE } from "../../lib/mockData";
import type { NewDocument } from "../../lib/types";
import Icon from "./Icon";

type Props = {
  onScan: (input: NewDocument) => void;
  error?: string | null;
};

export default function UploadStep({ onScan, error }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  // Set after mount so the server-rendered page and the browser agree on the date.
  const [defaultTitle, setDefaultTitle] = useState("Visit note");
  useEffect(() => {
    setDefaultTitle(`Visit note, ${new Date().toLocaleDateString("en-CA", { month: "short", day: "numeric" })}`);
  }, []);

  const pick = (f: File | undefined) => {
    if (f && (f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"))) setFile(f);
  };
  const canScan = file !== null || text.trim().length > 0;
  const scan = () => {
    if (file) onScan({ kind: "pdf", file });
    else if (text.trim()) onScan({ kind: "paste", title: title.trim() || defaultTitle, text });
  };

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel__head">
          <div>
            <h2>Upload or paste a note</h2>
            <p>Text-based PDF, or paste the note text.</p>
          </div>
        </div>
        <div className="panel__body">
          <div
            className={`dropzone ${dragging ? "is-dragging" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pick(e.dataTransfer.files[0]);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(e) => pick(e.target.files?.[0])}
            />
            <div className="dropzone__icon">
              <Icon name="upload" size={22} />
            </div>
            {file ? (
              <>
                <div>
                  <span className="file-chip">
                    <Icon name="file" />
                    <span className="mono">{file.name}</span>
                    <span className="muted">{Math.max(1, Math.round(file.size / 1024))} KB</span>
                  </span>
                </div>
                <p className="dropzone__hint">Click to choose a different file</p>
              </>
            ) : (
              <>
                <div className="dropzone__title">Drop a PDF here</div>
                <p className="dropzone__hint">Scanned PDFs are not supported yet.</p>
                <span className="btn">
                  <Icon name="file" /> Choose a file
                </span>
              </>
            )}
          </div>

          <div className="or-divider">or paste text</div>

          <label className="field">
            <span className="field__label">Document title</span>
            <input
              className="input"
              value={title}
              placeholder={defaultTitle}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field__label">Note text</span>
            <textarea
              className="textarea"
              rows={5}
              value={text}
              placeholder="Paste the note here"
              onChange={(e) => setText(e.target.value)}
            />
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <div className="actions">
            <button type="button" className="btn btn--primary" disabled={!canScan} onClick={scan}>
              Scan document
            </button>
            {file && (
              <button type="button" className="link-btn" onClick={() => setFile(null)}>
                Remove PDF
              </button>
            )}
            <button
              type="button"
              className="link-btn"
              onClick={() => {
                setFile(null);
                setTitle(DEMO_TITLE);
                setText(DEMO_NOTE);
              }}
            >
              Use the demo note
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
