"use client";

import { apiUrl, responseDetail } from "./api";

/** localStorage flag set once a visitor finishes (or skips) the journey. */
export const ONBOARDED_KEY = "ta_onboarded";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, init);
  if (!response.ok) throw new Error(await responseDetail(response));
  return (await response.json()) as T;
}

function json(init: RequestInit = {}, body: unknown): RequestInit {
  return {
    ...init,
    method: init.method ?? "POST",
    headers: { "Content-Type": "application/json", ...init.headers },
    body: JSON.stringify(body),
  };
}

export type DemoSystemStatus = {
  system_id: string;
  status: string;
  baseline_status: string;
  baseline_pct: number;
  baseline_patterns: number;
  auto_fix_allowed: boolean;
};

export type DemoStatus = {
  shop: DemoSystemStatus | null;
  freezer: DemoSystemStatus | null;
  scenario_playing: boolean;
  last_run_id: string | null;
  pr_url: string | null;
};

export type SetupProfile = {
  system_id: string;
  name: string;
  kind: string;
  appliance_type?: string | null;
  owner_contact?: string;
  environment?: Record<string, string>;
  normal_ranges?: Record<string, unknown>[];
  expected_behaviours?: Record<string, unknown>[];
  modes?: Record<string, unknown>[];
  failure_definitions?: Record<string, unknown>[];
  hard_limits?: Record<string, unknown>[];
  policy?: {
    allowed_actions?: string[];
    forbidden_actions?: string[];
    auto_fix_allowed?: boolean;
    countdown_s?: number;
    alert_contacts?: string[];
  };
  baseline?: { status?: string };
  status: string;
  version: number;
};

export type SetupConflict = {
  field: string;
  key: string;
  values: { doc?: string; value?: unknown; quote?: string }[];
};

export type DocumentsResult = {
  profile: SetupProfile;
  conflicts: SetupConflict[];
  rejected: string[];
  needs_manual: string[];
  fallback: boolean;
};

export async function apiHealth(timeoutMs = 3000): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const response = await fetch(`${apiUrl}/api/health`, {
      signal: ctrl.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

/** J1: ensure the two demo systems exist (idempotent). */
export async function demoBootstrap(): Promise<{
  shop: SetupProfile;
  freezer: SetupProfile;
}> {
  return req("/api/demo/bootstrap", { method: "POST" });
}

/** J1: one pollable snapshot for the journey. */
export async function demoStatus(): Promise<DemoStatus> {
  return req("/api/demo/status");
}

/** J2: read the server's manuals for one demo system. */
export async function demoDocuments(
  systemId: string,
): Promise<DocumentsResult> {
  return req(`/api/demo/${encodeURIComponent(systemId)}/documents`, {
    method: "POST",
  });
}

/** J3: 120 s learning window with gentle traffic, server-side. */
export async function demoLearn(systemId: string): Promise<{
  system_id: string;
  status: string;
  started_at: number;
  ends_at: number;
  driver: string;
}> {
  return req(
    `/api/demo/${encodeURIComponent(systemId)}/learn`,
    json({}, {}),
  );
}

export async function getProfile(systemId: string): Promise<{
  profile: SetupProfile;
  conflicts: SetupConflict[];
  feedback: unknown[];
}> {
  return req(`/api/systems/${encodeURIComponent(systemId)}/profile`);
}

export async function putProfile(
  systemId: string,
  profile: SetupProfile,
): Promise<SetupProfile> {
  return req(
    `/api/systems/${encodeURIComponent(systemId)}/profile`,
    json({ method: "PUT" }, profile),
  );
}

export async function confirmProfile(
  systemId: string,
  confirmedBy: string,
  resolve: { field: string; key: string; pick: unknown }[] = [],
): Promise<SetupProfile> {
  return req(
    `/api/systems/${encodeURIComponent(systemId)}/profile/confirm`,
    json({}, { confirmed_by: confirmedBy, resolve }),
  );
}

export async function armSystem(systemId: string): Promise<SetupProfile> {
  return req(`/api/systems/${encodeURIComponent(systemId)}/arm`, {
    method: "POST",
  });
}

/** Stop a learning window early (the guided setup's Skip path uses this). */
export async function finishBaseline(systemId: string): Promise<unknown> {
  return req(`/api/systems/${encodeURIComponent(systemId)}/baseline/finish`, {
    method: "POST",
  });
}
