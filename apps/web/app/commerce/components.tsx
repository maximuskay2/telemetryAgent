// Presentational commerce components (C-N3/C-N5). Pure props in,
// markup out — pages wire them to the §8.4 API via useSession.
"use client";

import { useState } from "react";
import {
  CommerceError,
  Device,
  Member,
  Org,
  Role,
  Usage,
  blockedReasons,
} from "../lib/commerce";
import { Card } from "../ui";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="text-sm text-text-muted">{label}</p>;
}

export function ApiErrorView({ error }: { error: unknown }) {
  if (error instanceof CommerceError && error.status === 401) {
    return (
      <Card title="Sign in required">
        <p className="text-sm text-text-muted">
          This page needs an account.{" "}
          <a href="/signin?next=/connect" className="text-brand-cyan">
            Sign in
          </a>
        </p>
      </Card>
    );
  }
  if (error instanceof CommerceError && error.status === 403) {
    return (
      <Card title="Not allowed">
        <p className="text-sm text-text-muted">
          Your role can&apos;t do that. Ask an admin.
        </p>
      </Card>
    );
  }
  const message =
    error instanceof Error ? error.message : "Something went wrong.";
  return (
    <Card title="Couldn't load">
      <p className="text-sm text-text-muted">{message}</p>
    </Card>
  );
}

const ROLE_TONE: Record<Role, string> = {
  owner: "border-brand/40 bg-brand/10 text-brand-cyan",
  admin: "border-ok/40 bg-ok/10 text-ok",
  member: "border-border bg-surface-2 text-text-muted",
  viewer: "border-border bg-surface-2 text-text-faint",
};

export function RoleBadge({ role }: { role: Role }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${ROLE_TONE[role]}`}
    >
      {role}
    </span>
  );
}

export function OrgSwitcher({
  orgs,
  activeId,
  onSwitch,
}: {
  orgs: Org[];
  activeId: string | null;
  onSwitch: (orgId: string) => void;
}) {
  if (orgs.length === 0) return null;
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-text-muted">
      Org
      <select
        aria-label="Organization"
        value={activeId ?? ""}
        onChange={(event) => onSwitch(event.target.value)}
        className="cursor-pointer rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-[13px] text-text outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        {orgs.map((org) => (
          <option key={org.id} value={org.id}>
            {org.name} ({org.role})
          </option>
        ))}
      </select>
    </label>
  );
}

export function MemberList({
  members,
  selfId,
  canManage,
  onRemove,
  onTransfer,
}: {
  members: Member[];
  selfId: string | null;
  canManage: boolean;
  onRemove: (userId: string) => void;
  onTransfer: (userId: string) => void;
}) {
  if (members.length === 0) {
    return <p className="text-sm text-text-muted">No members yet.</p>;
  }
  return (
    <ul className="divide-y divide-border">
      {members.map((member) => (
        <li
          key={member.user_id}
          className="flex flex-wrap items-center gap-2 py-2"
        >
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-text">
              {member.name}{" "}
              <span className="text-text-muted">{member.email}</span>
            </p>
          </div>
          <RoleBadge role={member.role} />
          {canManage &&
            member.user_id !== selfId &&
            member.role !== "owner" && (
              <>
                <button
                  type="button"
                  onClick={() => onTransfer(member.user_id)}
                  className="cursor-pointer rounded-md border border-border px-2 py-1 text-xs text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
                >
                  Make owner
                </button>
                <button
                  type="button"
                  onClick={() => onRemove(member.user_id)}
                  className="cursor-pointer rounded-md border border-crit/40 px-2 py-1 text-xs text-crit outline-none hover:bg-crit/10 focus-visible:ring-2 focus-visible:ring-crit"
                >
                  Remove
                </button>
              </>
            )}
        </li>
      ))}
    </ul>
  );
}

export function InviteForm({ onInvite }: { onInvite: (email: string, role: Role) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onInvite(email, role);
        setEmail("");
      }}
      className="flex flex-wrap items-end gap-2"
    >
      <label className="flex flex-col gap-1 text-xs text-text-muted">
        Email
        <input
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="teammate@company.co"
          className="w-56 rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-[13px] text-text outline-none focus-visible:ring-2 focus-visible:ring-brand"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-text-muted">
        Role
        <select
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          className="cursor-pointer rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-[13px] text-text outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <option value="admin">admin</option>
          <option value="member">member</option>
          <option value="viewer">viewer</option>
        </select>
      </label>
      <button
        type="submit"
        className="cursor-pointer rounded-lg bg-brand px-3 py-1.5 text-[13px] font-medium text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
      >
        Invite
      </button>
    </form>
  );
}

export function DeviceList({
  devices,
  canManage,
  onRevoke,
}: {
  devices: Device[];
  canManage: boolean;
  onRevoke: (deviceId: string) => void;
}) {
  if (devices.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        No phones paired yet. Pair one below.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-border">
      {devices.map((device) => (
        <li key={device.id} className="flex flex-wrap items-center gap-2 py-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-text">{device.label}</p>
            <p className="font-mono text-[11px] text-text-faint">{device.id}</p>
          </div>
          {device.revoked ? (
            <span className="inline-flex items-center rounded-full border border-crit/40 bg-crit/10 px-2 py-0.5 text-[11px] font-medium text-crit">
              revoked
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full border border-ok/40 bg-ok/10 px-2 py-0.5 text-[11px] font-medium text-ok">
              active
            </span>
          )}
          {canManage && !device.revoked && (
            <button
              type="button"
              onClick={() => onRevoke(device.id)}
              className="cursor-pointer rounded-md border border-crit/40 px-2 py-1 text-xs text-crit outline-none hover:bg-crit/10 focus-visible:ring-2 focus-visible:ring-crit"
            >
              Revoke
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

export function PairCodeView({
  code,
  expiresIn,
}: {
  code: string;
  expiresIn: string;
}) {
  return (
    <div className="rounded-lg border border-brand/40 bg-brand/10 p-3 text-center">
      <p className="text-xs text-text-muted">
        Enter this code on your phone · expires in {expiresIn}
      </p>
      <p className="mt-1 font-mono text-3xl tracking-[0.2em] text-text">
        {code}
      </p>
    </div>
  );
}

function UsageBar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const over = used >= limit;
  return (
    <div
      role="progressbar"
      aria-valuenow={used}
      aria-valuemin={0}
      aria-valuemax={limit}
      className="h-2 overflow-hidden rounded-full bg-surface-2"
    >
      <div
        className={`h-full rounded-full ${over ? "bg-crit" : "bg-brand"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function UsageView({ usage }: { usage: Usage }) {
  const reasons = blockedReasons(usage);
  const rows: Array<{ label: string; used: number; limit: number }> = [
    { label: "Fix runs", used: usage.fix_runs_used, limit: usage.fix_runs_limit },
    { label: "Systems", used: usage.systems_used, limit: usage.systems_limit },
    { label: "Devices", used: usage.devices_used, limit: usage.devices_limit },
  ];
  const languages = Object.entries(usage.by_language).sort((a, b) =>
    a[0].localeCompare(b[0]),
  );
  return (
    <div className="space-y-4">
      {reasons.length > 0 && (
        <div
          role="alert"
          className="rounded-lg border border-warn/40 bg-warn/10 p-3"
        >
          {reasons.map((reason) => (
            <p key={reason} className="text-sm text-text">
              {reason}
            </p>
          ))}
          <p className="mt-1 text-xs text-text-muted">
            Monitoring and alerts continue; new fix runs wait for next month.
          </p>
        </div>
      )}
      {rows.map((row) => (
        <div key={row.label}>
          <p className="mb-1 flex items-baseline justify-between text-sm">
            <span className="text-text">{row.label}</span>
            <span className="text-xs text-text-muted tabular-nums">
              {row.used} of {row.limit} free
            </span>
          </p>
          <UsageBar used={row.used} limit={row.limit} />
        </div>
      ))}
      {languages.length > 0 && (
        <div>
          <p className="mb-1 text-sm text-text">Fix runs by language</p>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {languages.map(([language, stats]) => (
              <li
                key={language}
                className="flex items-baseline justify-between px-3 py-1.5 text-sm"
              >
                <span className="text-text">{language}</span>
                <span className="text-xs text-text-muted tabular-nums">
                  {stats.fix_runs} runs
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
