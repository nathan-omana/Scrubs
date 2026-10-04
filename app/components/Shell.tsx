import { USE_MOCK } from "../../lib/api";
import HowItWorks from "./HowItWorks";

export type Step = "upload" | "review" | "chat";
export type Notice = { text: string; retry?: () => void };

const STEPS: { key: Step; label: string }[] = [
  { key: "upload", label: "Upload document" },
  { key: "review", label: "Review redactions" },
  { key: "chat", label: "Ask the chatbot" },
];

type Props = {
  step: Step;
  enabled: Record<Step, boolean>;
  onSelect: (s: Step) => void;
  title: string;
  subtitle?: string;
  alert?: Notice | null;
  children: React.ReactNode;
};

export default function Shell({ step, enabled, onSelect, title, subtitle, alert, children }: Props) {
  const current = STEPS.findIndex((s) => s.key === step);

  return (
    <div className="app">
      <header className="masthead">
        <div className="container masthead__inner">
          <div className="wordmark">
            <span className="wordmark__mark" aria-hidden>
              S
            </span>
            Scrubs
          </div>
          <div className="masthead__right">
            <HowItWorks />
            <span className="masthead__user">Dr. A. Singh · Hope Family Clinic</span>
          </div>
        </div>
      </header>

      <main className="container content">
        <ol className="steps" aria-label="Progress">
          {STEPS.map((s, i) => {
            const state = i < current ? "done" : i === current ? "current" : "todo";
            return (
              <li key={s.key} className={`steps__item steps__item--${state}`} aria-current={i === current ? "step" : undefined}>
                <span className="steps__num">{i + 1}</span>
                {enabled[s.key] && i !== current ? (
                  <button type="button" className="steps__link" onClick={() => onSelect(s.key)}>
                    {s.label}
                  </button>
                ) : (
                  <span className="steps__label">{s.label}</span>
                )}
              </li>
            );
          })}
        </ol>

        <div className="page-head">
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>

        {alert && (
          <p className="form-error notice" role="alert">
            {alert.text}{" "}
            {alert.retry && (
              <button type="button" className="link-btn" onClick={alert.retry}>
                Try again
              </button>
            )}
          </p>
        )}
        {children}
      </main>

      {USE_MOCK && (
        <footer className="footer">
          <div className="container">Demo mode: sample data, no backend.</div>
        </footer>
      )}
    </div>
  );
}
