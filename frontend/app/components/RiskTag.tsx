import type { Risk } from "../../lib/mockData";

const LABEL: Record<Risk, string> = { HIGH: "HIGH", MEDIUM: "MED", LOW: "LOW" };

export default function RiskTag({ risk }: { risk: Risk }) {
  return <span className={`scrubs-tag scrubs-tag--${risk.toLowerCase()}`}>{LABEL[risk]}</span>;
}
