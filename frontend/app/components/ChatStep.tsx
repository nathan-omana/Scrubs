"use client";

import { useEffect, useRef, useState } from "react";
import { CANNED_REPLIES, entitiesOf } from "../../lib/mockData";
import type { ContextDoc } from "../page";

type Props = {
  contextDocs: ContextDoc[];
  setContextDocs: React.Dispatch<React.SetStateAction<ContextDoc[]>>;
  onBack: () => void;
  onAddDocument: () => void;
  onEditDocument: (cd: ContextDoc) => void;
};

type Message = { role: "user" | "assistant"; aiSaw: string; youSee: string };

const SUGGESTIONS = [
  "Summarize the discharge plan",
  "Any interactions between the discharge medications?",
  "Compare medications across the loaded documents",
];

const replaceAll = (text: string, from: string, to: string) => text.split(from).join(to);

export default function ChatStep({ contextDocs, setContextDocs, onBack, onAddDocument, onEditDocument }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [split, setSplit] = useState(true);
  const replyCount = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);

  const active = contextDocs.filter((d) => d.active);
  const activeEntities = active.flatMap((d) => entitiesOf(d.doc).map((ent) => ({ ent, masked: d.masked[ent.id] })));

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, thinking]);

  // Outgoing: swap real values the user typed for pseudonyms before "sending".
  const pseudonymize = (text: string) =>
    activeEntities.reduce((t, { ent, masked }) => (masked ? replaceAll(t, ent.text, ent.pseudonym) : t), text);

  // Incoming: Gemini only ever saw pseudonyms for masked items and real text for kept items.
  const asGeminiSaw = (text: string) =>
    activeEntities.reduce((t, { ent, masked }) => (masked ? t : replaceAll(t, ent.pseudonym, ent.text)), text);
  const reidentify = (text: string) =>
    activeEntities.reduce((t, { ent }) => replaceAll(t, ent.pseudonym, ent.text), text);

  const send = (text: string) => {
    if (!text.trim() || thinking || active.length === 0) return;
    setMessages((m) => [...m, { role: "user", youSee: text, aiSaw: pseudonymize(text) }]);
    setDraft("");
    setThinking(true);
    setTimeout(() => {
      const raw = CANNED_REPLIES[replyCount.current++ % CANNED_REPLIES.length];
      setMessages((m) => [...m, { role: "assistant", aiSaw: asGeminiSaw(raw), youSee: reidentify(raw) }]);
      setThinking(false);
    }, 1100);
  };

  const toggleActive = (id: string) =>
    setContextDocs((docs) => docs.map((d) => (d.doc.id === id ? { ...d, active: !d.active } : d)));
  const remove = (id: string) => setContextDocs((docs) => docs.filter((d) => d.doc.id !== id));

  return (
    <div className="scrubs-chat">
      <div className="scrubs-toolbar">
        <div className="display-flex flex-align-center">
          <button type="button" className="usa-button usa-button--outline margin-right-2" onClick={onBack}>
            Back
          </button>
          <div>
            <h1 className="scrubs-h1 margin-bottom-0">Ask Gemini</h1>
            <div className="text-base">
              Using {active.length} of {contextDocs.length} document{contextDocs.length === 1 ? "" : "s"} · pseudonymized
            </div>
          </div>
        </div>

        <div className="scrubs-toolbar__actions">
          <label className="scrubs-switch">
            <input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} />
            Show what the AI saw
          </label>

          <div className="scrubs-menu">
            <button
              type="button"
              className="usa-button usa-button--secondary-alt scrubs-menu__trigger"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
            >
              Context ({active.length}) ▾
            </button>
            {menuOpen && (
              <div className="scrubs-menu__panel" role="dialog" aria-label="Context documents">
                <div className="scrubs-menu__head">
                  <span className="text-bold">Documents in context</span>
                  <button type="button" className="usa-button usa-button--unstyled" onClick={() => setMenuOpen(false)}>
                    Close
                  </button>
                </div>
                <ul className="scrubs-menu__list">
                  {contextDocs.map((cd) => {
                    const ents = entitiesOf(cd.doc);
                    const n = ents.filter((x) => cd.masked[x.id]).length;
                    return (
                      <li key={cd.doc.id}>
                        <label className="scrubs-menu__doc">
                          <input type="checkbox" checked={cd.active} onChange={() => toggleActive(cd.doc.id)} />
                          <span>
                            <span className="text-bold">{cd.doc.title}</span>
                            <span className="scrubs-mono scrubs-menu__file">{cd.doc.fileName}</span>
                            <span className="text-base">
                              {n} of {ents.length} items masked
                            </span>
                          </span>
                        </label>
                        <div className="scrubs-menu__doc-actions">
                          <button type="button" className="usa-button usa-button--unstyled" onClick={() => onEditDocument(cd)}>
                            Edit redactions
                          </button>
                          <button
                            type="button"
                            className="usa-button usa-button--unstyled scrubs-danger-link"
                            onClick={() => remove(cd.doc.id)}
                          >
                            Remove
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <button type="button" className="usa-button usa-button--outline width-full" onClick={onAddDocument}>
                  + Add another document
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="scrubs-panel scrubs-panel--flush">
        {split && (
          <div className="scrubs-split-head">
            <div>What you see</div>
            <div>What the AI saw</div>
          </div>
        )}
        <div className="scrubs-messages">
          {messages.length === 0 && (
            <div className="scrubs-empty">
              <p className="margin-top-0">
                Gemini has the pseudonymized text of the selected documents. Names you type are swapped for pseudonyms
                before sending, and answers are re-identified on your device.
              </p>
              <div className="scrubs-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="scrubs-suggestion" onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`scrubs-msg-row ${split ? "is-split" : ""}`}>
              <div className={`scrubs-msg scrubs-msg--${m.role}`}>
                <div className="scrubs-msg__who">{m.role === "user" ? "You" : "Gemini"}</div>
                <div className="scrubs-msg__body">{m.youSee}</div>
              </div>
              {split && (
                <div className={`scrubs-msg scrubs-msg--${m.role} scrubs-msg--ai-view`}>
                  <div className="scrubs-msg__who">{m.role === "user" ? "Sent" : "Received"}</div>
                  <div className="scrubs-msg__body scrubs-mono-soft">{m.aiSaw}</div>
                </div>
              )}
            </div>
          ))}
          {thinking && <div className="scrubs-thinking">Gemini is answering…</div>}
          <div ref={endRef} />
        </div>

        <form
          className="scrubs-composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
        >
          <label className="usa-sr-only" htmlFor="chat-input">
            Message
          </label>
          <textarea
            id="chat-input"
            className="usa-textarea scrubs-composer__input"
            rows={2}
            placeholder={active.length ? "Ask about these documents…" : "Select at least one document in Context"}
            value={draft}
            disabled={active.length === 0}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
          />
          <button type="submit" className="usa-button" disabled={!draft.trim() || thinking || active.length === 0}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
