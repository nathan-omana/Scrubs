"use client";

import { useEffect, useRef, useState } from "react";
import { chat, getMapping } from "../../lib/api";
import { replaceAll, splitOn, wordCount } from "../../lib/text";
import type { Doc } from "../../lib/types";
import Icon from "./Icon";

export type ChatMessage =
  | { role: "user"; text: string; sent: string; mapping: Record<string, string> }
  | { role: "assistant"; answer: string; mapping: Record<string, string>; outbound: string; identifierCount: number };

type Props = {
  readyDocs: Doc[];
  selectedIds: string[];
  setSelectedIds: (ids: string[]) => void;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  onAddDocument: () => void;
  onReview: (doc: Doc) => void;
};

const PROMPTS = [
  { label: "Referral letter", text: "Draft a referral letter to cardiology." },
  { label: "Discharge summary", text: "Write a discharge summary." },
  { label: "Handoff note", text: "Write a shift handoff note." },
];

// Pseudonyms swapped back to real values. Unknown pseudonyms stay as written.
function YouSee({ text, mapping }: { text: string; mapping: Record<string, string> }) {
  return (
    <>
      {splitOn(text, Object.keys(mapping)).map((p, i) =>
        p.key ? (
          <span key={i} className="reid" title={`Gemini saw ${p.key}`}>
            {mapping[p.key]}
          </span>
        ) : (
          p.text
        ),
      )}
    </>
  );
}

function AiSaw({ text, mapping }: { text: string; mapping: Record<string, string> }) {
  return (
    <>
      {splitOn(text, Object.keys(mapping)).map((p, i) =>
        p.key ? (
          <span key={i} className="pseudo">
            {p.key}
          </span>
        ) : (
          p.text
        ),
      )}
    </>
  );
}

export default function ChatStep({
  readyDocs,
  selectedIds,
  setSelectedIds,
  messages,
  setMessages,
  onAddDocument,
  onReview,
}: Props) {
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [split, setSplit] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  const active = readyDocs.filter((d) => selectedIds.includes(d.id));
  const activeFlags = active.flatMap((d) => d.flags);
  const canSend = active.length > 0 && !thinking;

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), [messages, thinking]);

  const toggleDoc = (id: string) =>
    setSelectedIds(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]);

  const send = async (text: string) => {
    if (!text.trim() || !canSend) return;
    const ids = active.map((d) => d.id);
    setDraft("");
    setThinking(true);
    try {
      const mapping: Record<string, string> = Object.assign({}, ...(await Promise.all(ids.map(getMapping))));
      const sent = replaceAll(text, Object.entries(mapping).map(([pseudo, real]) => [real, pseudo]));
      setMessages((m) => [...m, { role: "user", text, sent, mapping }]);
      const res = await chat(ids, text);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          answer: res.answer_with_pseudonyms,
          mapping,
          outbound: res.outbound_text,
          identifierCount: res.identifier_count,
        },
      ]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="chat-grid">
      <aside className="chat-side">
        <section className="panel">
          <div className="panel__head">
            <div>
              <h2>Documents</h2>
              <p>Only checked documents are sent</p>
            </div>
            <span className="badge badge--ready">{active.length} selected</span>
          </div>
          {readyDocs.length === 0 ? (
            <p className="empty">No reviewed documents yet.</p>
          ) : (
            <ul className="check-list">
              {readyDocs.map((doc) => (
                <li key={doc.id}>
                  <label className="check-item">
                    <input type="checkbox" checked={selectedIds.includes(doc.id)} onChange={() => toggleDoc(doc.id)} />
                    <span className="check-item__body">
                      <span className="check-item__title">{doc.title}</span>
                      <span className="check-item__meta">
                        {doc.flags.filter((f) => f.masked).length} items masked ·{" "}
                        <button type="button" className="link-btn" onClick={() => onReview(doc)}>
                          Review
                        </button>
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className="panel__foot">
            <button type="button" className="link-btn" onClick={onAddDocument}>
              <Icon name="plus" size={14} /> Add document
            </button>
          </div>
        </section>

        <section className="panel">
          <div className="panel__head">
            <h2>What Gemini receives</h2>
          </div>
          <dl className="stat-list">
            <div>
              <dt>Items masked</dt>
              <dd>{activeFlags.filter((f) => f.masked).length}</dd>
            </div>
            <div>
              <dt>Changed from default</dt>
              <dd>{activeFlags.filter((f) => f.masked !== (f.tier !== "low")).length}</dd>
            </div>
            <div>
              <dt>Dates shifted</dt>
              <dd>{activeFlags.filter((f) => f.masked && f.label === "Date").length}</dd>
            </div>
            <div>
              <dt>Text sent</dt>
              <dd>Pseudonymized only</dd>
            </div>
          </dl>
        </section>
      </aside>

      <section className="panel chat-panel">
        <div className="panel__head panel__head--wrap">
          <div>
            <h2>Ask Gemini</h2>
            <p>Answers are re-identified on your screen. Gemini never sees real values.</p>
          </div>
          <div className="toolbar__actions">
            <div className="prompt-row">
              {PROMPTS.map((p) => (
                <button key={p.label} type="button" className="btn btn--sm" disabled={!canSend} onClick={() => send(p.text)}>
                  {p.label}
                </button>
              ))}
            </div>
            <label className="checkbox">
              <input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} />
              Split view
            </label>
          </div>
        </div>

        {split && messages.length > 0 && (
          <div className="split-head">
            <span>What you see</span>
            <span>What the AI saw</span>
          </div>
        )}

        <div className="messages">
          {messages.length === 0 && (
            <div className="chat-empty">
              <p>
                {active.length === 0
                  ? "Check at least one document to start."
                  : "Ask for a referral letter, a discharge summary, or a handoff note. Gemini only gets the pseudonymized text of the checked documents."}
              </p>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className={`msg-row ${split ? "is-split" : ""}`}>
                <div className="bubble bubble--user">
                  <div className="bubble__who">You</div>
                  {m.text}
                </div>
                {split && (
                  <div className="bubble bubble--user is-ai-view">
                    <div className="bubble__who">Sent to Gemini</div>
                    <AiSaw text={m.sent} mapping={m.mapping} />
                  </div>
                )}
              </div>
            ) : (
              <div key={i} className={`msg-row ${split ? "is-split" : ""}`}>
                {m.identifierCount > 0 ? (
                  <div className="outbound outbound--blocked">
                    Not sent. The leak check found {m.identifierCount} identifier{m.identifierCount === 1 ? "" : "s"} in
                    the outbound text.
                  </div>
                ) : (
                  <>
                    <div className="bubble bubble--answer">
                      <div className="bubble__who">Gemini · re-identified on your screen</div>
                      <YouSee text={m.answer} mapping={m.mapping} />
                    </div>
                    {split && (
                      <div className="bubble bubble--answer is-ai-view">
                        <div className="bubble__who">What Gemini wrote</div>
                        <AiSaw text={m.answer} mapping={m.mapping} />
                      </div>
                    )}
                  </>
                )}
                <details className="outbound">
                  <summary>
                    Sent to Gemini: {wordCount(m.outbound)} words, {m.identifierCount} identifiers
                  </summary>
                  <pre>{m.outbound}</pre>
                </details>
              </div>
            ),
          )}
          {thinking && <p className="thinking">Gemini is writing…</p>}
          <div ref={endRef} />
        </div>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
        >
          <label className="sr-only" htmlFor="chat-input">
            Message
          </label>
          <textarea
            id="chat-input"
            className="textarea"
            rows={1}
            value={draft}
            disabled={active.length === 0}
            placeholder={active.length ? "Ask a question or request a summary" : "Check a document first"}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
          />
          <button type="submit" className="btn btn--primary btn--icon" aria-label="Send" disabled={!draft.trim() || !canSend}>
            <Icon name="send" />
          </button>
        </form>
      </section>
    </div>
  );
}
