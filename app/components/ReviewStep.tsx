"use client";

import { useEffect, useState } from "react";
import { segmentsOf } from "../../lib/text";
import type { Doc, Flag, Tier } from "../../lib/types";
import Icon from "./Icon";
import TierTag from "./TierTag";

type Props = {
  doc: Doc;
  onSetMasked: (flag: Flag, masked: boolean) => void;
  onSetMany: (changes: [Flag, boolean][]) => void;
  onReset: () => void;
  onBack: () => void;
  onDone: () => void;
};

const tooltip = (f: Flag) =>
  `${f.label} · ${f.flag_code} · ${f.tier.toUpperCase()} · ${f.locked ? "always masked" : f.masked ? "masked, click to keep" : "kept, click to mask"}`;
const spanId = (f: Flag) => `span-${f.flag_code}`;
const rowId = (f: Flag) => `row-${f.flag_code}`;
const reveal = (id: string) => document.getElementById(id)?.scrollIntoView({ block: "nearest", behavior: "smooth" });

export default function ReviewStep({ doc, onSetMasked, onSetMany, onReset, onBack, onDone }: Props) {
  const [showAI, setShowAI] = useState(false);
  const [filter, setFilter] = useState<Tier | "all">("all");
  const [selected, setSelected] = useState<string | null>(null);

  const rows = doc.flags.filter((f) => filter === "all" || f.tier === filter);
  const count = (t: Tier) => doc.flags.filter((f) => f.tier === t).length;
  const maskedCount = doc.flags.filter((f) => f.masked).length;

  const toggle = (f: Flag) => {
    setSelected(f.flag_code);
    if (!f.locked) onSetMasked(f, !f.masked);
  };
  const setTier = (tier: Tier, masked: boolean) =>
    onSetMany(doc.flags.filter((f) => f.tier === tier && !f.locked && f.masked !== masked).map((f) => [f, masked]));

  // Clicking a highlight toggles it and scrolls its row into view, and the other way round.
  const clickSpan = (f: Flag) => {
    toggle(f);
    if (filter !== "all" && filter !== f.tier) setFilter("all");
    requestAnimationFrame(() => reveal(rowId(f)));
  };
  const clickRow = (f: Flag) => {
    toggle(f);
    reveal(spanId(f));
  };

  // J / K moves through the list, M masks or unmasks the selected item.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || target.matches("input, textarea")) return;
      const i = rows.findIndex((f) => f.flag_code === selected);
      const key = e.key.toLowerCase();
      if (key === "j" || key === "k") {
        const next = rows[key === "j" ? Math.min(i + 1, rows.length - 1) : Math.max(i - 1, 0)];
        if (next) {
          setSelected(next.flag_code);
          reveal(rowId(next));
          reveal(spanId(next));
        }
      } else if (key === "m" && rows[i]) {
        toggle(rows[i]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <>
      <div className="review-head">
        <div>
          <h2 className="review-head__title">{doc.title}</h2>
          <p className="review-head__meta">
            {doc.source === "pdf" ? "PDF upload" : "Pasted text"} · {doc.flags.length} items flagged ·{" "}
            <strong>{maskedCount} will be masked</strong>
          </p>
        </div>
        <div className="review-head__actions">
          <button type="button" className="btn" onClick={onBack}>
            Back
          </button>
          <button type="button" className="btn btn--primary" onClick={onDone}>
            Continue
          </button>
        </div>
      </div>

      <div className="review-grid">
        <section className="panel doc-panel" aria-label="Document">
          <div className="panel__head">
            <h2>{showAI ? "What the chatbot will see" : "Original document"}</h2>
            <div className="segmented" role="group" aria-label="Document view">
              <button type="button" aria-pressed={!showAI} onClick={() => setShowAI(false)}>
                Original
              </button>
              <button type="button" aria-pressed={showAI} onClick={() => setShowAI(true)}>
                What the chatbot will see
              </button>
            </div>
          </div>

          <div className="page__text doc-panel__text">
            {segmentsOf(doc).map((seg, i) => {
              if (typeof seg === "string") return <span key={i}>{seg}</span>;
              const f = seg;
              return (
                <button
                  key={f.flag_code}
                  id={spanId(f)}
                  type="button"
                  className={[
                    "span",
                    `span--${f.tier}`,
                    f.masked ? "is-masked" : "is-kept",
                    f.locked ? "is-locked" : "",
                    selected === f.flag_code ? "is-selected" : "",
                  ].join(" ")}
                  title={tooltip(f)}
                  aria-pressed={f.masked}
                  onClick={() => clickSpan(f)}
                >
                  {showAI && f.masked ? <span className="span__pseudo">{f.pseudonym}</span> : f.text}
                </button>
              );
            })}
          </div>

          <div className="panel__foot doc-panel__foot">
            <span>Click a highlighted item to mask or keep it. Solid highlight = masked, dashed outline = kept.</span>
            <span className="legend">
              <span className="legend__item">
                <TierTag tier="high" /> always masked
              </span>
              <span className="legend__item">
                <TierTag tier="med" /> masked by default
              </span>
              <span className="legend__item">
                <TierTag tier="low" /> kept by default
              </span>
            </span>
          </div>
        </section>

        <section className="panel flags" aria-label="Flagged items">
          <div className="panel__head">
            <h2>Flagged items</h2>
            <button type="button" className="link-btn" onClick={onReset}>
              Reset to defaults
            </button>
          </div>

          <div className="filters" role="group" aria-label="Filter by tier">
            {(["all", "high", "med", "low"] as const).map((t) => (
              <button key={t} type="button" className="filter" aria-pressed={filter === t} onClick={() => setFilter(t)}>
                {t === "all" ? "All" : t[0].toUpperCase() + t.slice(1)} ({t === "all" ? doc.flags.length : count(t)})
              </button>
            ))}
          </div>

          <div className="bulk">
            <span>Mask all:</span>
            {(["med", "low"] as const).map((tier) => {
              const editable = doc.flags.filter((f) => f.tier === tier && !f.locked);
              const on = editable.length > 0 && editable.every((f) => f.masked);
              return (
                <button
                  key={tier}
                  type="button"
                  role="switch"
                  aria-checked={on}
                  aria-label={`Mask all ${tier.toUpperCase()} items`}
                  className="switch"
                  disabled={editable.length === 0}
                  onClick={() => setTier(tier, !on)}
                >
                  <span className="switch__track">
                    <span className="switch__thumb" />
                  </span>
                  <TierTag tier={tier} />
                </button>
              );
            })}
          </div>

          <div className="flag-table-wrap">
            <table className="flag-table">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">Risk</th>
                  <th scope="col">Replace with</th>
                  <th scope="col">Masked</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="empty">
                      Nothing flagged at this tier.
                    </td>
                  </tr>
                )}
                {rows.map((f) => (
                  <tr
                    key={f.flag_code}
                    id={rowId(f)}
                    className={[selected === f.flag_code ? "is-selected" : "", f.locked ? "is-locked" : ""].join(" ")}
                    onClick={() => clickRow(f)}
                  >
                    <td>
                      <div className="flag-table__text">{f.text}</div>
                      <div className="flag-table__meta">
                        {f.label} · <span className="mono">{f.flag_code}</span>
                      </div>
                    </td>
                    <td>
                      <TierTag tier={f.tier} />
                    </td>
                    <td className="mono flag-table__to">{f.masked ? f.pseudonym : <span className="muted">as written</span>}</td>
                    <td>
                      {f.locked ? (
                        <span className="locked" title="HIGH items are always masked">
                          <Icon name="lock" size={14} /> Locked
                        </span>
                      ) : (
                        <button
                          type="button"
                          role="switch"
                          aria-checked={f.masked}
                          aria-label={`${f.masked ? "Keep" : "Mask"} ${f.text}`}
                          className="switch"
                          onClick={(e) => {
                            e.stopPropagation();
                            toggle(f);
                          }}
                        >
                          <span className="switch__track">
                            <span className="switch__thumb" />
                          </span>
                          <span className="switch__label">{f.masked ? "On" : "Off"}</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel__foot">
            <span className="kbd-hint">J / K</span> next item · <span className="kbd-hint">M</span> mask or keep
          </div>
        </section>
      </div>
    </>
  );
}
