// Production connections API client (N-R4). Reads only; generated keys are
// shown once by the caller and never stored in the browser.
import { apiUrl, responseDetail } from "../lib/api";
import type {
  ConnectionCreated,
  ConnectionKind,
  ConnectionList,
  ConnectionTest,
  ProdConnection,
} from "../types/production";

const CODE_KEY = "ta_connect_code";

/** Thrown on 401 so the page can ask for the access code again. */
export class AccessCodeError extends Error {}

export function getAccessCode(): string {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem(CODE_KEY) ?? "";
}

export function setAccessCode(code: string): void {
  if (code) window.sessionStorage.setItem(CODE_KEY, code);
  else window.sessionStorage.removeItem(CODE_KEY);
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const code = getAccessCode();
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(code ? { "X-Connect-Code": code } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (response.status === 401 && path.startsWith("/api/connections")) {
    setAccessCode("");
    throw new AccessCodeError(await responseDetail(response));
  }
  if (!response.ok) throw new Error(await responseDetail(response));
  return (await response.json()) as T;
}

export type ConnectDoor = { enabled: boolean; codeRequired: boolean };

export async function getConnectDoor(): Promise<ConnectDoor> {
  const body = await req<{ enabled: boolean; code_required?: boolean }>(
    "/api/connections/enabled",
  );
  return {
    enabled: body.enabled === true,
    codeRequired: body.code_required === true,
  };
}

export async function getConnectEnabled(): Promise<boolean> {
  return (await getConnectDoor()).enabled;
}

/** True if the code opens the door; stores it for this tab on success. */
export async function checkAccessCode(code: string): Promise<boolean> {
  setAccessCode(code);
  try {
    await req("/api/connections/code", { method: "POST" });
    return true;
  } catch (err) {
    if (err instanceof AccessCodeError) return false;
    setAccessCode("");
    throw err;
  }
}

export type CreatedSystem = {
  system_id: string;
  name: string;
  kind: string;
};

export async function createSystem(input: {
  name: string;
  kind: "software" | "appliance";
  appliance_type?: "fridge" | "freezer";
  owner_contact?: string;
}): Promise<CreatedSystem> {
  return req("/api/systems", { method: "POST", body: JSON.stringify(input) });
}

export async function createConnection(input: {
  system_id: string;
  kind: ConnectionKind;
  config?: Record<string, unknown>;
  secret?: string;
}): Promise<ConnectionCreated> {
  return req("/api/connections", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listConnections(
  systemId: string,
): Promise<ProdConnection[]> {
  const body = await req<ConnectionList>(
    `/api/connections?system_id=${encodeURIComponent(systemId)}`,
  );
  return body.connections;
}

export async function testConnection(id: string): Promise<ConnectionTest> {
  return req(`/api/connections/${encodeURIComponent(id)}/test`, {
    method: "POST",
  });
}

export async function deleteConnection(id: string): Promise<void> {
  await req(`/api/connections/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// No native rotate endpoint: rotate = delete + create with the same config.
// The old key dies at once; the new key is shown once like any create.
// Pasted-secret kinds (github/railway/webhook) need the secret re-entered.
export async function rotateConnection(
  conn: ProdConnection,
  secret?: string,
): Promise<ConnectionCreated> {
  await deleteConnection(conn.id);
  return createConnection({
    system_id: conn.system_id,
    kind: conn.kind,
    config: conn.config,
    secret,
  });
}

export async function pairingUrl(): Promise<string> {
  const response = await fetch(`${apiUrl}/api/pairing`);
  if (!response.ok) throw new Error(await responseDetail(response));
  const body = (await response.json()) as { api_url?: unknown };
  if (typeof body.api_url !== "string") {
    throw new Error("Pairing URL unavailable.");
  }
  return body.api_url;
}
