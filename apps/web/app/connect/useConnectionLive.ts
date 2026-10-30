// Minimal live socket for the /connect wizard (N-R4): connection_status flips
// only. The shared useAgentStream hook drops unknown kinds, so the wizard
// keeps its own tiny socket instead of touching shared files.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { wsUrl } from "../lib/api";
import { listConnections } from "./api";

export type LiveFlip = { status: string; detail: string };

export function useConnectionLive(systemId: string | null) {
  const [flips, setFlips] = useState<Record<string, LiveFlip>>({});
  const [live, setLive] = useState(false);
  const systemRef = useRef(systemId);
  systemRef.current = systemId;

  useEffect(() => {
    if (!systemId) return;
    let socket: WebSocket | null = null;
    let closed = false;
    try {
      socket = new WebSocket(wsUrl());
    } catch {
      return;
    }
    socket.onopen = () => {
      if (!closed) setLive(true);
    };
    socket.onclose = () => {
      if (!closed) setLive(false);
    };
    socket.onerror = () => {
      if (!closed) setLive(false);
    };
    socket.onmessage = (event) => {
      if (closed) return;
      try {
        const frame = JSON.parse(String(event.data)) as {
          kind?: unknown;
          payload?: unknown;
        };
        if (frame.kind !== "connection_status") return;
        if (typeof frame.payload !== "object" || !frame.payload) return;
        const p = frame.payload as Record<string, unknown>;
        if (p["system_id"] !== systemRef.current) return;
        const id = p["connection_id"];
        if (typeof id !== "string") return;
        setFlips((prev) => ({
          ...prev,
          [id]: {
            status: String(p["status"] ?? ""),
            detail: String(p["detail"] ?? ""),
          },
        }));
      } catch {
        // Ignore malformed frames; recheck() covers missed flips.
      }
    };
    return () => {
      closed = true;
      socket?.close();
    };
  }, [systemId]);

  // Fallback when the socket is down: merge stored ok statuses as flips.
  const recheck = useCallback(async () => {
    if (!systemId) return;
    try {
      const conns = await listConnections(systemId);
      setFlips((prev) => {
        const next = { ...prev };
        for (const c of conns) {
          if (c.status === "ok") {
            next[c.id] = { status: c.status, detail: c.detail };
          }
        }
        return next;
      });
    } catch {
      // Surface keeps waiting; the user retries.
    }
  }, [systemId]);

  return { flips, live, recheck };
}
