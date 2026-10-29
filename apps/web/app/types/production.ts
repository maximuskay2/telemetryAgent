// Production-route contracts (production-roadmap §3.4, frozen at H0).
// Hand-mirrored from core/schemas/production.py; JSON keys stay snake_case
// exactly as the API sends them.

export type ConnectionKind =
  | "logs"
  | "sentry"
  | "github"
  | "railway"
  | "webhook"
  | "device";

export type ConnectionStatus = "waiting" | "ok" | "error";

export type OptionKind =
  | "open_pr"
  | "rollback"
  | "restart"
  | "remote"
  | "manual"
  | "dispatch";

export type OptionStatus =
  | "available"
  | "sent"
  | "done"
  | "failed"
  | "expired"
  | "cancelled";

export type DeviceAction = "defrost" | "setpoint" | "power_cycle" | "backup_on";

export type RunDomain = "software" | "appliance";

export type ProdConnection = {
  id: string;
  system_id: string;
  kind: ConnectionKind;
  config: Record<string, unknown>;
  secret_hint: string;
  status: ConnectionStatus;
  detail: string;
  last_seen: number;
};

export type ConnectionCreated = {
  connection: ProdConnection;
  key?: string;
};

export type ConnectionList = {
  connections: ProdConnection[];
};

export type ConnectionTest = {
  ok: boolean;
  detail: string;
  permissions?: { read: boolean; pull_requests: boolean };
};

export type OptionSafety = {
  ok: boolean;
  reason: string;
};

export type ProdOption = {
  id: string;
  kind: OptionKind;
  title: string;
  detail: string;
  url: string;
  safety: OptionSafety;
  status: OptionStatus;
};

export type IncidentOptions = {
  run_id: string;
  domain: RunDomain;
  options: ProdOption[];
};

export type OptionExecuted = {
  status: string;
  command_id: string;
};

export type DeviceCommand = {
  id: string;
  action: DeviceAction;
  params: Record<string, unknown>;
  expires_at: number;
};

export type CommandList = {
  commands: DeviceCommand[];
};

export type AckResult = {
  status: string;
};

export type EnabledResult = {
  enabled: boolean;
};

export type PauseState = {
  paused: boolean;
};

export type SuiteSummary = {
  passed: number;
  failed: number;
  new_failures: number;
};

export type MitigationSummary = {
  action: string;
  status: string;
};

export type SoftwareRunResult = {
  pr_url: string;
  repo: string;
  suite?: SuiteSummary;
  mitigation?: MitigationSummary;
};

// New WebSocket event payloads (§3.4).
export type ConnectionStatusEvent = {
  connection_id: string;
  system_id: string;
  status: string;
  detail: string;
};

export type OptionStatusEvent = {
  run_id: string;
  option_id: string;
  status: string;
  detail: string;
};

export type ActionsPausedEvent = {
  paused: boolean;
};

export type PrOpenedEvent = {
  run_id: string;
  system_id: string;
  pr_url: string;
  repo: string;
};
