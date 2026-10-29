import type { GateDecision } from "../../types/api";

export type GateGroup = {
  key: string;
  decision: GateDecision;
  count: number;
};

/** Collapse repeats: same rule + fingerprint + decision counts as one card. */
export function groupGateDecisions(decisions: GateDecision[]): GateGroup[] {
  const groups: GateGroup[] = [];
  for (const decision of decisions) {
    const key = `${decision.decision}|${decision.rule}|${decision.fingerprint}`;
    const existing = groups.find((g) => g.key === key);
    if (existing) {
      existing.count += 1;
      if (decision.ts > existing.decision.ts) existing.decision = decision;
    } else {
      groups.push({ key, decision, count: 1 });
    }
  }
  return groups;
}
