"use client";

import { useRef, useState } from "react";
import { DEMO_NOTE, DEMO_TITLE } from "../../lib/mockData";
import type { Doc, NewDocument } from "../../lib/types";
import Icon from "./Icon";
import TierTag, { tierCounts } from "./TierTag";

type Props = {
  docs: Doc[];
  onScan: (input: NewDocument) => void;
  onOpen: (doc: Doc) => void;
  error?: string | null;
};

const formatAdded = (iso: string) => {
  const d = new Date(iso);
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(iso).setHours(0, 0, 0, 0)) / 86_400_000);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (days === 0) return `Today, ${time}`;
  if (days === 1) return `Yesterday, ${time}`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
};

export default function UploadStep({ docs, onScan, onOpen, error }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  const pick = (f: File | undefined) => {
    if (f && (f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"))) setFile(f);
  };
  const canScan = file !== null || text.trim().length > 0;
  const scan = () => {
    if (file) onScan({ kind: "pdf", file });
    else if (text.trim()) onScan({ kind: "paste", title, text });
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
              placeholder="Visit note, Sept 28"
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

      <section className="panel">
        <div className="panel__head">
          <div>
            <h2>Scanned documents</h2>
            <p>Open one to review it, or to use it in chat once it is ready.</p>
          </div>
        </div>
        {docs.length === 0 ? (
          <p className="empty">No documents yet.</p>
        ) : (
          <ul className="doc-list">
            {docs.map((doc) => (
              <li key={doc.id}>
                <div className="doc-row">
                  <span className="doc-row__icon">
                    <Icon name={doc.source === "pdf" ? "file" : "paste"} />
                  </span>
                  <div className="doc-row__main">
                    <div className="doc-row__title">{doc.title}</div>
                    <div className="doc-row__meta">
                      {doc.source === "pdf" ? "PDF upload" : "Pasted text"} · {formatAdded(doc.created_at)}
                    </div>
                  </div>
                  <div className="doc-row__right">
                    <span className="tier-counts">
                      {tierCounts(doc.flags).map(({ tier, count }) => (
                        <TierTag key={tier} tier={tier} count={count} />
                      ))}
                    </span>
                    {doc.status === "ready" ? (
                      <span className="badge badge--ready">
                        <Icon name="check" size={12} /> Ready
                      </span>
                    ) : (
                      <span className="badge">Needs review</span>
                    )}
                    <button type="button" className="btn btn--sm" onClick={() => onOpen(doc)}>
                      Review
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
