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

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) throw new Error(await responseDetail(response));
  return (await response.json()) as T;
}

export async function getConnectEnabled(): Promise<boolean> {
  const body = await req<{ enabled: boolean }>("/api/connections/enabled");
  return body.enabled === true;
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
