import type { Step } from "../page";

const STEPS: { key: Step; label: string }[] = [
  { key: "upload", label: "Upload document" },
  { key: "review", label: "Review redactions" },
  { key: "chat", label: "Ask Gemini" },
];

type Props = {
  step: Step;
  canReview: boolean;
  canChat: boolean;
  onSelect: (s: Step) => void;
};

export default function StepIndicator({ step, canReview, canChat, onSelect }: Props) {
  const currentIndex = STEPS.findIndex((s) => s.key === step);
  const enabled = { upload: true, review: canReview, chat: canChat };

  return (
    <div className="usa-step-indicator usa-step-indicator--counters-sm scrubs-steps" aria-label="progress">
      <ol className="usa-step-indicator__segments">
        {STEPS.map((s, i) => {
          const status =
            i < currentIndex ? "usa-step-indicator__segment--complete" : i === currentIndex ? "usa-step-indicator__segment--current" : "";
          return (
            <li key={s.key} className={`usa-step-indicator__segment ${status}`} aria-current={i === currentIndex ? "step" : undefined}>
              <span className="usa-step-indicator__segment-label">
                {enabled[s.key] && i !== currentIndex ? (
                  <button type="button" className="scrubs-link-button" onClick={() => onSelect(s.key)}>
                    {s.label}
                  </button>
                ) : (
                  s.label
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
