// In-memory §8.4 backend for development, screenshots and tests.
// Active only when NEXT_PUBLIC_COMMERCE_MOCK=1 (dev-only; the real
// backend answers the same JSON). Enforces the frozen role matrix so
// 403 paths are exercisable without a server.

import {
  CommerceApi,
  CommerceError,
  Device,
  Invite,
  Member,
  Org,
  PairCode,
  Role,
  Usage,
} from "./commerce";

const ROLES: Role[] = ["owner", "admin", "member", "viewer"];

function roleAtLeast(role: Role, minimum: Role): boolean {
  return ROLES.indexOf(role) <= ROLES.indexOf(minimum);
}

export class MockCommerceApi implements CommerceApi {
  private orgs: Org[] = [
    { id: "org_acme", name: "Acme", role: "owner", created_at: 0 },
    { id: "org_demo", name: "Demo", role: "viewer", created_at: 0 },
  ];
  private members: Record<string, Member[]> = {
    org_acme: [
      { user_id: "usr_1", email: "ada@acme.co", name: "Ada", role: "owner" },
      { user_id: "usr_2", email: "bob@acme.co", name: "Bob", role: "admin" },
      {
        user_id: "usr_3",
        email: "cat@acme.co",
        name: "Cat",
        role: "member",
      },
    ],
    org_demo: [
      { user_id: "usr_1", email: "ada@acme.co", name: "Ada", role: "viewer" },
    ],
  };
  private devices: Record<string, Device[]> = {
    org_acme: [
      {
        id: "dev_1",
        label: "Ada's Pixel",
        created_at: 0,
        last_used_at: 0,
        revoked: false,
      },
    ],
    org_demo: [],
  };
  private invites: Record<string, { orgId: string; role: Role }> = {};
  private inviteSeq = 0;
  private pairSeq = 0;
  role: Role = "owner";

  private org(id: string): Org {
    const found = this.orgs.find((o) => o.id === id);
    if (!found) throw new CommerceError(404, "API returned 404");
    return { ...found, role: this.role };
  }

  private need(minimum: Role) {
    if (!roleAtLeast(this.role, minimum)) {
      throw new CommerceError(403, "API returned 403");
    }
  }

  async listOrgs() {
    return { orgs: this.orgs.map((o) => ({ ...o })) };
  }

  async createOrg(name: string) {
    const org: Org = {
      id: `org_${Date.now()}`,
      name,
      role: "owner",
      created_at: 0,
    };
    this.orgs.push(org);
    this.members[org.id] = [];
    this.devices[org.id] = [];
    return { org };
  }

  async getOrg(id: string) {
    const org = this.org(id);
    return { org, role: org.role };
  }

  async deleteOrg(id: string) {
    this.need("owner");
    this.org(id);
    this.orgs = this.orgs.filter((o) => o.id !== id);
    return { deleted: true, grace_until: 0 };
  }

  async listMembers(orgId: string) {
    this.org(orgId);
    return { members: (this.members[orgId] ?? []).map((m) => ({ ...m })) };
  }

  async inviteMember(
    orgId: string,
    email: string,
    role: Role,
  ): Promise<{ invite: Invite }> {
    this.need("admin");
    this.org(orgId);
    if (role === "owner") throw new CommerceError(403, "API returned 403");
    this.inviteSeq += 1;
    const token = `inv_mock_${this.inviteSeq}`;
    this.invites[token] = { orgId, role };
    return { invite: { token, expires_at: 0 } };
  }

  async acceptInvite(token: string) {
    const invite = this.invites[token];
    if (!invite) throw new CommerceError(404, "API returned 404");
    return { org_id: invite.orgId, role: invite.role };
  }

  async removeMember(orgId: string, userId: string) {
    this.need("admin");
    const members = this.members[orgId] ?? [];
    const target = members.find((m) => m.user_id === userId);
    if (!target) throw new CommerceError(404, "API returned 404");
    if (target.role === "owner") {
      throw new CommerceError(403, "API returned 403");
    }
    this.members[orgId] = members.filter((m) => m.user_id !== userId);
    return { removed: true };
  }

  async transferOwnership(orgId: string, userId: string) {
    this.need("owner");
    const members = this.members[orgId] ?? [];
    if (!members.some((m) => m.user_id === userId)) {
      throw new CommerceError(404, "API returned 404");
    }
    return { ok: true };
  }

  async pairDevice(orgId: string, label: string): Promise<PairCode> {
    this.need("member");
    this.org(orgId);
    if (!label.trim()) throw new CommerceError(400, "API returned 400");
    this.pairSeq += 1;
    return {
      code: `123-45${this.pairSeq % 10}`,
      expires_at: Math.floor(Date.now() / 1000) + 600,
    };
  }

  async claimDevice(code: string) {
    if (!/^\d{3}-\d{3}$/.test(code.trim())) {
      throw new CommerceError(400, "API returned 400");
    }
    return { device_token: "ta_dev_mock", org_id: "org_acme" };
  }

  async listDevices(orgId: string) {
    this.org(orgId);
    return { devices: (this.devices[orgId] ?? []).map((d) => ({ ...d })) };
  }

  async revokeDevice(orgId: string, deviceId: string) {
    this.need("admin");
    const devices = this.devices[orgId] ?? [];
    const target = devices.find((d) => d.id === deviceId);
    if (!target) throw new CommerceError(404, "API returned 404");
    target.revoked = true;
    return { revoked: true };
  }

  async getUsage(orgId: string): Promise<Usage> {
    this.org(orgId);
    return {
      fix_runs_used: 3,
      fix_runs_limit: 30,
      cost_used_usd: 1.2,
      cost_ceiling_usd: 25.0,
      systems_used: 1,
      systems_limit: 3,
      devices_used: 1,
      devices_limit: 5,
      by_language: { python: { fix_runs: 3, cost_usd: 1.2 } },
    };
  }
}
