"use client";

import { useState } from "react";
import { entitiesOf, defaultMasked, type Entity, type Risk, type ScrubbedDoc } from "../../lib/mockData";
import RiskTag from "./RiskTag";

type Props = {
  doc: ScrubbedDoc;
  masked: Record<string, boolean>;
  setMasked: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  onBack: () => void;
  onConfirm: () => void;
};

const RISK_ORDER: Risk[] = ["HIGH", "MEDIUM", "LOW"];

export default function ReviewStep({ doc, masked, setMasked, onBack, onConfirm }: Props) {
  const [view, setView] = useState<"original" | "redacted">("original");
  const [filter, setFilter] = useState<Risk | "ALL">("ALL");
  const [hovered, setHovered] = useState<string | null>(null);

  const entities = entitiesOf(doc);
  const rows = entities
    .filter((ent) => filter === "ALL" || ent.risk === filter)
    .sort((a, b) => RISK_ORDER.indexOf(a.risk) - RISK_ORDER.indexOf(b.risk));

  const toggle = (ent: Entity) => {
    if (ent.risk === "HIGH") return; // locked
    setMasked((m) => ({ ...m, [ent.id]: !m[ent.id] }));
  };
  const setAll = (risk: Risk, value: boolean) =>
    setMasked((m) => ({
      ...m,
      ...Object.fromEntries(entities.filter((x) => x.risk === risk).map((x) => [x.id, value])),
    }));
  const reset = () => setMasked(Object.fromEntries(entities.map((x) => [x.id, defaultMasked(x)])));

  const count = (risk: Risk) => entities.filter((x) => x.risk === risk).length;
  const maskedCount = entities.filter((x) => masked[x.id]).length;

  return (
    <>
      <div className="scrubs-toolbar">
        <div>
          <h1 className="scrubs-h1 margin-bottom-05">Review redactions</h1>
          <div className="text-base">
            <span className="scrubs-mono">{doc.fileName}</span> · {doc.pages} pages · {entities.length} items flagged ·{" "}
            <strong>{maskedCount} will be masked</strong>
          </div>
        </div>
        <div className="scrubs-toolbar__actions">
          <button type="button" className="usa-button usa-button--outline" onClick={onBack}>
            Back
          </button>
          <button type="button" className="usa-button" onClick={onConfirm}>
            Confirm and continue
          </button>
        </div>
      </div>

      <div className="grid-row grid-gap-lg">
        {/* Document */}
        <section className="grid-col-12 desktop:grid-col-7">
          <div className="scrubs-panel scrubs-panel--flush">
            <div className="scrubs-panel__header">
              <span className="text-bold">{doc.title}</span>
              <div className="scrubs-segmented" role="group" aria-label="Document view">
                <button
                  type="button"
                  aria-pressed={view === "original"}
                  onClick={() => setView("original")}
                >
                  Original
                </button>
                <button
                  type="button"
                  aria-pressed={view === "redacted"}
                  onClick={() => setView("redacted")}
                >
                  What Gemini will see
                </button>
              </div>
            </div>
            <div className="scrubs-document">
              {doc.segments.map((seg, i) => {
                if (typeof seg === "string") return <span key={i}>{seg}</span>;
                const isMasked = masked[seg.id];
                if (view === "redacted") {
                  return isMasked ? (
                    <span key={seg.id} className={`scrubs-pseudo scrubs-pseudo--${seg.risk.toLowerCase()}`}>
                      {seg.pseudonym}
                    </span>
                  ) : (
                    <span key={seg.id}>{seg.text}</span>
                  );
                }
                return (
                  <button
                    key={seg.id}
                    type="button"
                    className={[
                      "scrubs-span",
                      `scrubs-span--${seg.risk.toLowerCase()}`,
                      isMasked ? "is-masked" : "is-kept",
                      hovered === seg.id ? "is-hovered" : "",
                    ].join(" ")}
                    title={`${seg.type} · ${seg.risk} · ${isMasked ? "masked" : "kept"}${seg.risk === "HIGH" ? " (locked)" : ""}`}
                    onMouseEnter={() => setHovered(seg.id)}
                    onMouseLeave={() => setHovered(null)}
                    onClick={() => toggle(seg)}
                  >
                    {seg.text}
                  </button>
                );
              })}
            </div>
            <div className="scrubs-panel__footer text-base">
              Click a highlighted item to toggle it. Solid highlight = masked, dashed outline = kept.
            </div>
          </div>
        </section>

        {/* Flagged items */}
        <section className="grid-col-12 desktop:grid-col-5">
          <div className="scrubs-panel scrubs-panel--flush">
            <div className="scrubs-panel__header">
              <span className="text-bold">Flagged items</span>
              <button type="button" className="usa-button usa-button--unstyled" onClick={reset}>
                Reset to defaults
              </button>
            </div>

            <div className="scrubs-filters">
              {(["ALL", ...RISK_ORDER] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  className="scrubs-filter"
                  aria-pressed={filter === r}
                  onClick={() => setFilter(r)}
                >
                  {r === "ALL" ? `All (${entities.length})` : `${r === "MEDIUM" ? "Med" : r[0] + r.slice(1).toLowerCase()} (${count(r)})`}
                </button>
              ))}
            </div>

            <div className="scrubs-bulk">
              <span className="text-base">Bulk:</span>
              <button type="button" className="usa-button usa-button--unstyled" onClick={() => setAll("MEDIUM", false)}>
                Keep all MED
              </button>
              <button type="button" className="usa-button usa-button--unstyled" onClick={() => setAll("LOW", true)}>
                Mask all LOW
              </button>
            </div>

            <div className="scrubs-table-wrap">
              <table className="usa-table usa-table--borderless usa-table--compact scrubs-table">
                <thead>
                  <tr>
                    <th scope="col">Item</th>
                    <th scope="col">Risk</th>
                    <th scope="col">Replace with</th>
                    <th scope="col">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((ent) => (
                    <tr
                      key={ent.id}
                      className={hovered === ent.id ? "is-hovered" : ""}
                      onMouseEnter={() => setHovered(ent.id)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <td>
                        <div className="scrubs-item-text">{ent.text}</div>
                        <div className="scrubs-item-meta">
                          {ent.type} · {ent.source} · {Math.round(ent.confidence * 100)}%
                        </div>
                      </td>
                      <td>
                        <RiskTag risk={ent.risk} />
                      </td>
                      <td className="scrubs-mono">{ent.pseudonym}</td>
                      <td>
                        {ent.risk === "HIGH" ? (
                          <span className="scrubs-locked">Masked · locked</span>
                        ) : (
                          <div className="scrubs-segmented scrubs-segmented--sm" role="group">
                            <button
                              type="button"
                              aria-pressed={masked[ent.id]}
                              onClick={() => setMasked((m) => ({ ...m, [ent.id]: true }))}
                            >
                              Mask
                            </button>
                            <button
                              type="button"
                              aria-pressed={!masked[ent.id]}
                              onClick={() => setMasked((m) => ({ ...m, [ent.id]: false }))}
                            >
                              Keep
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
