"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import TierTag from "./TierTag";

export default function HowItWorks() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="popover" ref={ref}>
      <button
        type="button"
        className="btn btn--sm"
        aria-expanded={open}
        aria-controls="how-it-works"
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name="info" size={16} /> How it works
      </button>
      {open && (
        <div id="how-it-works" className="panel popover__panel" role="dialog" aria-label="How it works">
          <div className="popover__head">
            <h2>What happens when you scan</h2>
            <button type="button" className="link-btn" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <ol className="steps-list">
            <li>Presidio flags names, numbers, and dates.</li>
            <li>Our model and a list of BC places and roles flag indirect details Presidio misses, like &ldquo;the retired town pharmacist&rdquo;.</li>
            <li>Drug names, doses, and diagnoses are kept by default.</li>
            <li>You review every flagged item. Gemini only receives the pseudonymized text.</li>
          </ol>
          <h2 className="side-h">Tiers</h2>
          <dl className="tier-legend">
            <dt>
              <TierTag tier="high" />
            </dt>
            <dd>Always masked. Names, health card numbers, MRNs, addresses, phone numbers.</dd>
            <dt>
              <TierTag tier="med" />
            </dt>
            <dd>Masked by default. Exact dates, small towns, employers, unique roles, family details.</dd>
            <dt>
              <TierTag tier="low" />
            </dt>
            <dd>Kept by default. Drugs, doses, diagnoses, lab values.</dd>
          </dl>
        </div>
      )}
    </div>
  );
}
