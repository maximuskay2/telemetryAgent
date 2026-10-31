// Commerce API client (C-N3). Typed mirror of the frozen §8.4 JSON.
// Auth: session JWT via getToken (Clerk when keys land — see NEEDS;
// dev sessions in mock mode). Throws CommerceError (with status) so
// pages can render 401/403/404 states.

import { apiUrl, responseDetail } from "./api";

export type Role = "owner" | "admin" | "member" | "viewer";

export type Org = {
  id: string;
  name: string;
  role: Role;
  created_at?: number;
};

export type Member = {
  user_id: string;
  email: string;
  name: string;
  role: Role;
};

export type Invite = { token: string; expires_at: number };

export type Device = {
  id: string;
  label: string;
  created_at: number;
  last_used_at: number;
  revoked: boolean;
};

export type PairCode = { code: string; expires_at: number };

export type Claim = { device_token: string; org_id: string };

export type Usage = {
  fix_runs_used: number;
  fix_runs_limit: number;
  cost_used_usd: number;
  cost_ceiling_usd: number;
  systems_used: number;
  systems_limit: number;
  devices_used: number;
  devices_limit: number;
  by_language: Record<string, { fix_runs: number; cost_usd: number }>;
};

export class CommerceError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export type FetchFn = (
  input: string,
  init?: RequestInit,
) => Promise<Response>;

export type CommerceApi = {
  listOrgs(): Promise<{ orgs: Org[] }>;
  createOrg(name: string): Promise<{ org: Org }>;
  getOrg(id: string): Promise<{ org: Org; role: Role }>;
  deleteOrg(id: string): Promise<{ deleted: boolean; grace_until: number }>;
  listMembers(orgId: string): Promise<{ members: Member[] }>;
  inviteMember(
    orgId: string,
    email: string,
    role: Role,
  ): Promise<{ invite: Invite }>;
  acceptInvite(token: string): Promise<{ org_id: string; role: Role }>;
  removeMember(orgId: string, userId: string): Promise<{ removed: boolean }>;
  transferOwnership(orgId: string, userId: string): Promise<{ ok: boolean }>;
  pairDevice(orgId: string, label: string): Promise<PairCode>;
  claimDevice(code: string): Promise<Claim>;
  listDevices(orgId: string): Promise<{ devices: Device[] }>;
  revokeDevice(orgId: string, deviceId: string): Promise<{ revoked: boolean }>;
  getUsage(orgId: string, period?: string): Promise<Usage>;
};

export class CommerceClient implements CommerceApi {
  private baseUrl: string;
  private getToken: () => string | null;
  private fetchFn: FetchFn;

  constructor(opts?: {
    baseUrl?: string;
    getToken?: () => string | null;
    fetchFn?: FetchFn;
  }) {
    this.baseUrl = opts?.baseUrl ?? apiUrl;
    this.getToken = opts?.getToken ?? (() => null);
    // Arrow wrapper: bare `fetch` detached from window throws
    // "Illegal invocation" in browsers.
    this.fetchFn =
      opts?.fetchFn ?? ((...args: Parameters<FetchFn>) => fetch(...args));
  }

  private async req<T>(path: string, init?: RequestInit): Promise<T> {
    const token = this.getToken();
    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      throw new CommerceError(response.status, await responseDetail(response));
    }
    return (await response.json()) as T;
  }

  listOrgs() {
    return this.req<{ orgs: Org[] }>("/api/orgs");
  }

  createOrg(name: string) {
    return this.req<{ org: Org }>("/api/orgs", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  getOrg(id: string) {
    return this.req<{ org: Org; role: Role }>(
      `/api/orgs/${encodeURIComponent(id)}`,
    );
  }

  deleteOrg(id: string) {
    return this.req<{ deleted: boolean; grace_until: number }>(
      `/api/orgs/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  }

  listMembers(orgId: string) {
    return this.req<{ members: Member[] }>(
      `/api/orgs/${encodeURIComponent(orgId)}/members`,
    );
  }

  inviteMember(orgId: string, email: string, role: Role) {
    return this.req<{ invite: Invite }>(
      `/api/orgs/${encodeURIComponent(orgId)}/invites`,
      { method: "POST", body: JSON.stringify({ email, role }) },
    );
  }

  acceptInvite(token: string) {
    return this.req<{ org_id: string; role: Role }>(
      `/api/invites/${encodeURIComponent(token)}/accept`,
      { method: "POST" },
    );
  }

  removeMember(orgId: string, userId: string) {
    return this.req<{ removed: boolean }>(
      `/api/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`,
      { method: "DELETE" },
    );
  }

  transferOwnership(orgId: string, userId: string) {
    return this.req<{ ok: boolean }>(
      `/api/orgs/${encodeURIComponent(orgId)}/transfer`,
      { method: "POST", body: JSON.stringify({ user_id: userId }) },
    );
  }

  pairDevice(orgId: string, label: string) {
    return this.req<PairCode>(
      `/api/orgs/${encodeURIComponent(orgId)}/devices/pair`,
      { method: "POST", body: JSON.stringify({ label }) },
    );
  }

  claimDevice(code: string) {
    return this.req<Claim>("/api/devices/claim", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
  }

  listDevices(orgId: string) {
    return this.req<{ devices: Device[] }>(
      `/api/orgs/${encodeURIComponent(orgId)}/devices`,
    );
  }

  revokeDevice(orgId: string, deviceId: string) {
    return this.req<{ revoked: boolean }>(
      `/api/orgs/${encodeURIComponent(orgId)}/devices/${encodeURIComponent(deviceId)}/revoke`,
      { method: "POST" },
    );
  }

  getUsage(orgId: string, period = "month") {
    return this.req<Usage>(
      `/api/orgs/${encodeURIComponent(orgId)}/usage?period=${encodeURIComponent(period)}`,
    );
  }
}

/** Why-blocked reasons from counts vs limits (no prices rendered). */
export function blockedReasons(usage: Usage): string[] {
  const reasons: string[] = [];
  if (usage.fix_runs_used >= usage.fix_runs_limit) {
    reasons.push(
      `Free allowance reached: ${usage.fix_runs_used}/${usage.fix_runs_limit} fix runs`,
    );
  }
  if (usage.cost_used_usd >= usage.cost_ceiling_usd) {
    reasons.push(
      `Free allowance reached: $${usage.cost_used_usd.toFixed(2)}/$${usage.cost_ceiling_usd.toFixed(2)} estimated cost`,
    );
  }
  if (usage.systems_used >= usage.systems_limit) {
    reasons.push(
      `Free allowance reached: ${usage.systems_used}/${usage.systems_limit} systems`,
    );
  }
  if (usage.devices_used >= usage.devices_limit) {
    reasons.push(
      `Free allowance reached: ${usage.devices_used}/${usage.devices_limit} devices`,
    );
  }
  return reasons;
}
