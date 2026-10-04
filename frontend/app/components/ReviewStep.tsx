"use client";

import { useEffect, useState } from "react";
import { segmentsOf } from "../../lib/text";
import type { Doc, Flag, Tier } from "../../lib/types";
import Icon from "./Icon";
import TierTag, { tierCounts } from "./TierTag";

type Props = {
  doc: Doc;
  onSetMasked: (flag: Flag, masked: boolean) => void;
  onReset: () => void;
  onDone: () => void;
};

const tooltip = (f: Flag) => `${f.label} · ${f.flag_code} · ${f.tier.toUpperCase()} · ${f.reason}`;
const spanId = (f: Flag) => `span-${f.flag_code}`;
const rowId = (f: Flag) => `row-${f.flag_code}`;
const reveal = (id: string) => document.getElementById(id)?.scrollIntoView({ block: "nearest", behavior: "smooth" });

export default function ReviewStep({ doc, onSetMasked, onReset, onDone }: Props) {
  const [showAI, setShowAI] = useState(false);
  const [filter, setFilter] = useState<Tier | "all">("all");
  const [selected, setSelected] = useState<string | null>(null);

  const rows = doc.flags.filter((f) => filter === "all" || f.tier === filter);
  const maskedCount = doc.flags.filter((f) => f.masked).length;
  const keptCount = doc.flags.length - maskedCount;

  const toggle = (f: Flag) => {
    if (!f.locked) onSetMasked(f, !f.masked);
  };
  const selectFromDoc = (f: Flag) => {
    setSelected(f.flag_code);
    if (filter !== "all" && filter !== f.tier) setFilter("all");
    requestAnimationFrame(() => reveal(rowId(f)));
  };
  const selectFromList = (f: Flag) => {
    setSelected(f.flag_code);
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
      <div className="toolbar">
        <div className="toolbar__doc">
          <h2>{doc.title}</h2>
          <p>{doc.source === "pdf" ? "PDF upload" : "Pasted text"}</p>
        </div>
        <div className="toolbar__actions">
          <span className="tier-counts" aria-label="Flagged items by tier">
            {tierCounts(doc.flags).map(({ tier, count }) => (
              <TierTag key={tier} tier={tier} count={count} />
            ))}
          </span>
          <label className="checkbox">
            <input type="checkbox" checked={showAI} onChange={(e) => setShowAI(e.target.checked)} />
            Show what the AI sees
          </label>
          <button type="button" className="btn btn--primary" onClick={onDone}>
            Done, open chat
          </button>
        </div>
      </div>

      <div className="review-grid">
        <section>
          <div className="legend">
            <span className="legend__title">Legend</span>
            <span className="legend__item">
              <TierTag tier="high" /> always masked
            </span>
            <span className="legend__item">
              <TierTag tier="med" /> masked by default
            </span>
            <span className="legend__item">
              <TierTag tier="low" /> kept by default
            </span>
            <span className="legend__item">
              <span className="swatch swatch--masked" /> masked
            </span>
            <span className="legend__item">
              <span className="swatch swatch--kept" /> sent as written
            </span>
          </div>

          <div className="panel page">
            <div className="page__label">
              <span>{showAI ? "What the AI sees" : "Original document"}</span>
            </div>
            <div className="page__text">
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
                      selected === f.flag_code ? "is-selected" : "",
                    ].join(" ")}
                    title={tooltip(f)}
                    onClick={() => selectFromDoc(f)}
                  >
                    {showAI && f.masked ? <span className="span__pseudo">{f.pseudonym}</span> : f.text}
                  </button>
                );
              })}
            </div>
          </div>

          <p className="summary">
            <Icon name="info" size={16} />
            {maskedCount} items masked, {keptCount} kept. Medications and diagnoses are kept unless you mask them.
          </p>
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
              <button
                key={t}
                type="button"
                className="filter"
                aria-pressed={filter === t}
                onClick={() => setFilter(t)}
              >
                {t === "all" ? "All" : t.toUpperCase()} ({t === "all" ? doc.flags.length : doc.flags.filter((f) => f.tier === t).length})
              </button>
            ))}
          </div>

          <ul className="flag-list">
            {rows.length === 0 && <li className="empty">Nothing flagged at this tier.</li>}
            {rows.map((f) => (
              <li
                key={f.flag_code}
                id={rowId(f)}
                className={`flag-row ${selected === f.flag_code ? "is-selected" : ""}`}
                onClick={() => selectFromList(f)}
              >
                <div className="flag-row__top">
                  <TierTag tier={f.tier} />
                  <span className="flag-row__label">{f.label}</span>
                  <span className="mono muted">{f.flag_code}</span>
                </div>
                <div className="flag-row__to">{f.masked ? `→ ${f.pseudonym}` : "sent as written"}</div>
                <div className="flag-row__text">&ldquo;{f.text}&rdquo;</div>
                <div className="flag-row__reason">
                  {f.reason}
                  {f.source === "model" && f.tier !== "low" && " · found by our model"}
                </div>
                <div className="flag-row__action">
                  {f.locked ? (
                    <span className="locked">
                      <Icon name="lock" size={14} /> Masked
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn--sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected(f.flag_code);
                        toggle(f);
                      }}
                    >
                      {f.masked ? "Unmask" : "Mask"}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>

          <div className="panel__foot">
            <span className="kbd-hint">J / K</span> next item · <span className="kbd-hint">M</span> mask or unmask
          </div>
        </section>
      </div>
    </>
  );
}
