"use client";

import { useCallback, useState } from "react";
import type { AgentStepEvent, LogEvent } from "../types/api";

export function feedItem(
  source: string,
  message: string,
  level: string,
  tag?: string,
): LogEvent {
  return {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    source,
    message,
    level,
    tag,
  };
}

function firstLine(text: string, max: number): string {
  const line = text.split("\n")[0].trim();
  return line.length > max ? `${line.slice(0, max)}…` : line;
}

export function watcherFeed(payload: {
  rule: string;
  level: string;
  domain: string;
  resource: string;
  matched_lines: string[];
}): LogEvent | null {
  const on = payload.resource ? ` on ${payload.resource}` : "";
  const detail = payload.matched_lines[0];
  const level = payload.level === "error" ? "ERROR" : "WARNING";
  const source = payload.domain === "appliance" ? "sensor-watcher" : "watcher";
  switch (payload.rule) {
    case "retry-cluster":
      return feedItem(source, `Watcher caught a retry storm${on}`, level);
    case "deadlock":
      return feedItem(source, `Watcher caught a deadlock${on}`, level);
    case "traceback":
      return feedItem(source, `Watcher caught a traceback${on}`, level);
    case "error":
      return feedItem(source, `Watcher caught an error${on}`, level);
    case "temp-warning":
    case "temp-critical":
    case "current-warning":
    case "current-spike":
      return feedItem(
        source,
        `Sensor watcher caught ${payload.rule}${detail ? `: ${detail}` : ""}`,
        level,
      );
    default:
      return feedItem(source, `Watcher caught ${payload.rule}${on}`, level);
  }
}

export function gateFeed(payload: {
  decision: string;
  reason: string;
  citation: string;
  rule: string;
}): LogEvent | null {
  const reason = payload.reason || "no reason given";
  const citation = payload.citation ? ` (${payload.citation})` : "";
  const rule = payload.rule ? ` [${payload.rule}]` : "";
  switch (payload.decision) {
    case "suppress":
      return feedItem("gate", `Gate suppressed${rule}: ${reason}${citation}`, "DEBUG");
    case "observe":
      return feedItem("gate", `Gate watching${rule}: ${reason}`, "WARNING");
    case "act":
      return feedItem("gate", `Gate escalated${rule}: ${reason}${citation}`, "ERROR");
    default:
      return null;
  }
}

export function stepFeed(msg: AgentStepEvent): LogEvent | null {
  const tag = msg.model || undefined;
  if (msg.step === "diagnose") {
    return feedItem(
      "agent",
      `Diagnosed: ${firstLine(msg.detail || msg.message, 140)}`,
      "INFO",
      tag,
    );
  }
  if (msg.step === "generate") {
    return feedItem("agent", `Wrote a fix (attempt ${msg.attempt})`, "INFO", tag);
  }
  if (msg.step === "verify") {
    const failed = msg.status === "FAIL" || msg.status === "error";
    return feedItem(
      "agent",
      `Sandbox verification: ${msg.status || "ran"}`,
      failed ? "ERROR" : "INFO",
      tag,
    );
  }
  if (msg.step === "done") {
    const failed = msg.status === "FAIL" || msg.status === "error";
    const noAction = msg.status === "NO_ACTION";
    const tail = msg.message ? ` — ${firstLine(msg.message, 120)}` : "";
    return feedItem(
      "agent",
      failed
        ? `Run finished: ${msg.status || "error"}${tail}`
        : noAction
          ? `Run finished: no action — normal behaviour${tail}`
          : `Run finished: verified fix${tail}`,
      failed ? "ERROR" : noAction ? "DEBUG" : "INFO",
      tag,
    );
  }
  return null;
}

export const FRIDGE_SENTENCES: Record<string, string> = {
  door_open: "Fridge door opened",
  condenser_fouling: "Condenser dirtied",
  power_surge: "Power surge injected",
  rapid_restart: "Rapid restart injected",
  close_door: "Fridge door closed",
  clean_condenser: "Condenser cleaned",
  reset: "Fridge reset",
};

export function useFeed() {
  const [events, setEvents] = useState<LogEvent[]>([]);
  const push = useCallback((item: LogEvent | null) => {
    if (!item) return;
    setEvents((current) => [...current.slice(-49), item]);
  }, []);
  const reset = useCallback(() => setEvents([]), []);
  return { events, push, setEvents, reset };
}
