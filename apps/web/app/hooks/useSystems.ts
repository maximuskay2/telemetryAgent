"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "../lib/api";
import { useSession } from "../lib/session";
import { refreshSessionAuth } from "../lib/sessionAuth";
import type { SystemSummary } from "../types/api";

type RawSystems = {
  systems?: {
    system_id?: unknown;
    name?: unknown;
    status?: unknown;
    kind?: unknown;
    environment?: unknown;
  }[];
};

function isDemo(environment: unknown): boolean {
  if (typeof environment !== "object" || environment === null) return false;
  return (environment as Record<string, unknown>).demo === "true";
}

function toSummaries(body: RawSystems): SystemSummary[] {
  return (body.systems ?? [])
    .filter(
      (
        s,
      ): s is {
        system_id: string;
        name: string;
        status: string;
        kind?: unknown;
        environment?: unknown;
      } =>
        typeof s.system_id === "string" &&
        typeof s.name === "string" &&
        typeof s.status === "string",
    )
    .map((s) => ({
      system_id: s.system_id,
      name: s.name,
      status: s.status,
      kind: typeof s.kind === "string" ? s.kind : "",
      demo: isDemo(s.environment),
    }));
}

export function useSystems() {
  const [systems, setSystems] = useState<SystemSummary[]>([]);
  const [systemsLoaded, setSystemsLoaded] = useState(false);
  const { getSessionAuth } = useSession();
  const lastKnown = useRef<SystemSummary[]>([]);

  const refreshSystems = useCallback(async () => {
    const load = async (freshToken?: string | null) => {
      const { token, orgId } = getSessionAuth();
      const bearer = freshToken ?? token;
      const response = await fetch(`${apiUrl}/api/systems`, {
        headers: {
          ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
          ...(orgId ? { "X-Org-Id": orgId } : {}),
        },
      });
      if (!response.ok) return null;
      const body = (await response.json()) as RawSystems;
      return { list: toSummaries(body), hadToken: Boolean(bearer) };
    };
    try {
      const first = await load();
      // HTTP error / API down: keep the last-known list, never blank it.
      if (!first) return;
      let list = first.list;
      if (
        list.length === 0 &&
        first.hadToken &&
        lastKnown.current.length > 0
      ) {
        // Suspicious: the systems endpoint degrades to 200-empty when
        // the token died mid-poll. One retry with a fresh token before
        // blanking provisioned systems out of the UI.
        const fresh = await refreshSessionAuth();
        if (fresh) {
          const second = await load(fresh);
          if (!second) return;
          list = second.list;
        }
      }
      lastKnown.current = list;
      setSystems(list);
      setSystemsLoaded(true);
    } catch {
      // API down; the banner stays hidden until systems load.
    }
  }, [getSessionAuth]);

  useEffect(() => {
    refreshSystems();
    const timer = window.setInterval(refreshSystems, 10000);
    return () => window.clearInterval(timer);
  }, [refreshSystems]);

  return { systems, systemsLoaded, refreshSystems };
}
