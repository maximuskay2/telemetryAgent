"use client";

import { useCallback, useEffect, useState } from "react";
import { apiUrl } from "../lib/api";
import { toGateDecision, type GateDecision, type LogEvent } from "../types/api";
import { gateFeed } from "./useFeed";

export type GateCounts = { suppress: number; observe: number; act: number };

const EMPTY_COUNTS: GateCounts = { suppress: 0, observe: 0, act: 0 };

function countDecisions(decisions: GateDecision[]): GateCounts {
  const counts = { ...EMPTY_COUNTS };
  for (const item of decisions) {
    if (item.decision === "suppress") counts.suppress += 1;
    else if (item.decision === "observe") counts.observe += 1;
    else if (item.decision === "act") counts.act += 1;
  }
  return counts;
}

export function useGate() {
  const [decisions, setDecisions] = useState<GateDecision[]>([]);
  const [counts, setCounts] = useState<GateCounts>(EMPTY_COUNTS);

  // Seed from the server log so counts survive refresh (S1).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/api/gate/decisions?limit=200`);
        if (!response.ok) return;
        const body = (await response.json()) as {
          decisions?: unknown[];
          counts?: unknown;
        };
        if (cancelled) return;
        const seeded = (body.decisions ?? [])
          .map(toGateDecision)
          .filter((d): d is GateDecision => d !== null);
        setDecisions(seeded);
        const raw = body.counts as Partial<GateCounts> | undefined;
        setCounts({
          suppress: typeof raw?.suppress === "number" ? raw.suppress : 0,
          observe: typeof raw?.observe === "number" ? raw.observe : 0,
          act: typeof raw?.act === "number" ? raw.act : 0,
        });
      } catch {
        // API down; live events still populate the log.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const applyGateDecision = useCallback(
    (payload: GateDecision): LogEvent | null => {
      setDecisions((current) => [payload, ...current].slice(0, 200));
      setCounts((current) => {
        const next = { ...current };
        if (payload.decision === "suppress") next.suppress += 1;
        else if (payload.decision === "observe") next.observe += 1;
        else if (payload.decision === "act") next.act += 1;
        return next;
      });
      return gateFeed(payload);
    },
    [],
  );

  const reset = useCallback(() => {
    setDecisions([]);
    setCounts({ ...EMPTY_COUNTS });
  }, []);

  return { decisions, counts, applyGateDecision, reset };
}
