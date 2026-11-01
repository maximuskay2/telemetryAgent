// Silent per-device demo session for the web dashboard.
//
// Anonymous demo vetoes (approve/disapprove on sim runs) must trace to a
// device, so the first anonymous dashboard visit pairs itself in the
// background: POST /api/demo/devices once per tab session, then attach the
// token as a fallback Authorization header. Signed-in sessions and the
// operator token always win (their headers spread later at the call site),
// so production traffic is untouched.
"use client";

import { apiUrl } from "./api";

const STORAGE_KEY = "ta.demo.device";
const LABEL = "web dashboard";

type StoredSession = { token: string; id: string };

let inflight: Promise<string | null> | null = null;

function readStored(): StoredSession | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (typeof parsed.token !== "string" || !parsed.token) return null;
    return {
      token: parsed.token,
      id: typeof parsed.id === "string" ? parsed.id : "",
    };
  } catch {
    return null;
  }
}

function storeSession(session: StoredSession): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Private mode: the token still works for this page load via inflight.
  }
}

/** Sync fallback headers for anonymous demo calls; {} when unpaired. */
export function demoAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const stored = readStored();
  return stored ? { Authorization: `Bearer ${stored.token}` } : {};
}

/** Pair this tab in the background; null when offline or unpaired. */
export async function ensureDemoDeviceToken(): Promise<string | null> {
  const stored = readStored();
  if (stored) return stored.token;
  if (!inflight) inflight = register();
  return inflight;
}

async function register(): Promise<string | null> {
  try {
    const response = await fetch(`${apiUrl}/api/demo/devices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: LABEL }),
    });
    if (!response.ok) return null;
    const data = (await response.json()) as {
      device_token?: unknown;
      device_id?: unknown;
    };
    if (typeof data.device_token !== "string" || !data.device_token) {
      return null;
    }
    storeSession({
      token: data.device_token,
      id: typeof data.device_id === "string" ? data.device_id : "",
    });
    return data.device_token;
  } catch {
    return null;
  } finally {
    inflight = null;
  }
}

/** Tell the API which demo systems this tab watches. Never throws. */
export async function declareDemoWatch(systems: string[]): Promise<void> {
  const token = await ensureDemoDeviceToken();
  if (!token) return;
  try {
    await fetch(`${apiUrl}/api/demo/devices/watch`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ systems }),
    });
  } catch {
    // Watch declaration is telemetry; a veto still carries the token.
  }
}
