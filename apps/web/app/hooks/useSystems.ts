"use client";

import { useCallback, useEffect, useState } from "react";
import { apiUrl } from "../lib/api";
import type { SystemSummary } from "../types/api";

export function useSystems() {
  const [systems, setSystems] = useState<SystemSummary[]>([]);
  const [systemsLoaded, setSystemsLoaded] = useState(false);

  const refreshSystems = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/api/systems`);
      if (!response.ok) return;
      const body = (await response.json()) as {
        systems?: {
          system_id?: unknown;
          name?: unknown;
          status?: unknown;
          kind?: unknown;
        }[];
      };
      setSystems(
        (body.systems ?? [])
          .filter(
            (s): s is {
              system_id: string;
              name: string;
              status: string;
              kind?: unknown;
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
          })),
      );
      setSystemsLoaded(true);
    } catch {
      // API down; the banner stays hidden until systems load.
    }
  }, []);

  useEffect(() => {
    refreshSystems();
    const timer = window.setInterval(refreshSystems, 10000);
    return () => window.clearInterval(timer);
  }, [refreshSystems]);

  return { systems, systemsLoaded, refreshSystems };
}
