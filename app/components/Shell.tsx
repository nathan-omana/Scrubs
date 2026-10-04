import { USE_MOCK } from "../../lib/api";
import HowItWorks from "./HowItWorks";
import Icon, { type IconName } from "./Icon";

export type Step = "upload" | "review" | "chat";
export type Notice = { text: string; retry?: () => void };

const STEPS: { key: Step; label: string; icon: IconName }[] = [
  { key: "upload", label: "Upload", icon: "upload" },
  { key: "review", label: "Review", icon: "review" },
  { key: "chat", label: "Chat", icon: "chat" },
];

type Props = {
  step: Step;
  enabled: Record<Step, boolean>;
  onSelect: (s: Step) => void;
  title: string;
  subtitle: string;
  alert?: Notice | null;
  children: React.ReactNode;
};

export default function Shell({ step, enabled, onSelect, title, subtitle, alert, children }: Props) {
  const current = STEPS.findIndex((s) => s.key === step);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark">
            <Icon name="shield" size={18} />
          </span>
          <div>
            <div className="brand__name">Scrubs</div>
            <div className="brand__sub">De-identify before AI</div>
          </div>
        </div>

        <nav aria-label="Steps">
          <div className="nav__label">Steps</div>
          <ol className="nav__list">
            {STEPS.map((s, i) => (
              <li key={s.key}>
                <button
                  type="button"
                  className="nav__item"
                  aria-current={i === current ? "step" : undefined}
                  disabled={!enabled[s.key]}
                  onClick={() => onSelect(s.key)}
                >
                  <Icon name={i < current ? "done" : s.icon} />
                  {s.label}
                  <span className="nav__num">{i + 1} of 3</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <div className="sidebar__foot">
          <strong>Synthetic data only</strong>
          <p>
            Gemini only receives pseudonymized text. Real values stay in your browser and the clinic&apos;s backend
            memory, and are cleared on restart.
          </p>
          {USE_MOCK && <p>Demo mode: sample data, no backend.</p>}
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <div className="topbar__title">
              <h1>{title}</h1>
              <span className="step-badge">
                Step {current + 1} of 3
              </span>
            </div>
            <p className="topbar__sub">{subtitle}</p>
          </div>
          <div className="topbar__right">
            <span className="topbar__user">Dr. A. Singh · Hope Family Clinic</span>
            <HowItWorks />
          </div>
        </header>
        <main className="content">
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
      </div>
    </div>
  );
}
