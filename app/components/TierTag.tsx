import type { Tier } from "../../lib/types";

export default function TierTag({ tier, count }: { tier: Tier; count?: number }) {
  return (
    <span className={`tier-tag tier-tag--${tier}`}>
      {tier.toUpperCase()}
      {count !== undefined && ` ${count}`}
    </span>
  );
}

export const tierCounts = (flags: { tier: Tier }[]) =>
  (["high", "med", "low"] as const).map((tier) => ({ tier, count: flags.filter((f) => f.tier === tier).length }));
