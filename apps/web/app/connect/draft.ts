// Incomplete /connect runs stay resumable drafts (per system) so a
// reload or a failed step never forces starting over.
export type WizardDraftData = {
  systemId: string;
  kind: string;
  name: string;
  repoPerms: { read: boolean; pull_requests: boolean } | null;
  hostingKind: string | null;
};

export type WizardDraft = {
  data: WizardDraftData;
  index: number;
  updatedAt: number;
};

export type DraftMap = Record<string, WizardDraft>;

type StringStore = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

const DRAFT_KEY = "ta_connect_drafts";

function webStore(): StringStore | null {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      return window.localStorage;
    }
  } catch {
    // private mode etc: fall through to null
  }
  return null;
}

export function loadDrafts(store?: StringStore | null): DraftMap {
  const storage = store === undefined ? webStore() : store;
  if (!storage) return {};
  try {
    const raw = storage.getItem(DRAFT_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed as DraftMap;
  } catch {
    return {};
  }
}

function writeDrafts(drafts: DraftMap, store?: StringStore | null): void {
  const storage = store === undefined ? webStore() : store;
  if (!storage) return;
  try {
    storage.setItem(DRAFT_KEY, JSON.stringify(drafts));
  } catch {
    // storage full/blocked: drafts are best-effort
  }
}

export function saveDraft(
  data: WizardDraftData,
  index: number,
  store?: StringStore | null,
): void {
  if (!data.systemId) return;
  const drafts = loadDrafts(store);
  drafts[data.systemId] = { data, index, updatedAt: Date.now() };
  writeDrafts(drafts, store);
}

export function clearDraft(
  systemId: string,
  store?: StringStore | null,
): void {
  const drafts = loadDrafts(store);
  if (!(systemId in drafts)) return;
  delete drafts[systemId];
  writeDrafts(drafts, store);
}

/** Wizard step names, shared by the picker and the mission gate. */
export const SOFTWARE_STEP_TITLES = [
  "System",
  "Logs",
  "Repo",
  "Teach",
  "Hosting",
  "Promise",
  "Pair",
  "Start",
];

export const APPLIANCE_STEP_TITLES = [
  "System",
  "Device",
  "Teach",
  "Promise",
  "Pair",
  "Start",
];

export function draftStepTitle(
  draft: WizardDraft,
  titles: string[],
): string {
  return titles[draft.index] ?? "Setup";
}

export type ServerSystem = {
  system_id: string;
  name: string;
  kind: string;
  status: string;
};

export type ResumeEntry =
  | { origin: "draft"; draft: WizardDraft }
  | { origin: "server"; system: ServerSystem };

/** Demo systems never resume through the production wizard (mirrors
 * mission/LeftPane DEMO_SYSTEM_IDS; self-hosted lists them too). */
const DEMO_SYSTEM_IDS = new Set(["autoparts-shop", "coldchain-1"]);

/**
 * One resume list from local drafts + the account's server systems.
 * A local draft wins on its exact step; a server system without one
 * resumes from its first step. Drafts for armed or vanished systems
 * are stale and drop out. systems === null (offline/failed fetch)
 * keeps every local draft so entry never blanks.
 */
export function mergeResumeEntries(
  drafts: DraftMap,
  systems: ServerSystem[] | null,
): ResumeEntry[] {
  const entries: ResumeEntry[] = [];
  if (systems === null) {
    return Object.values(drafts)
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .map((draft) => ({ origin: "draft", draft }) as ResumeEntry);
  }
  const byId = new Map(systems.map((s) => [s.system_id, s]));
  const kept = new Set<string>();
  for (const draft of Object.values(drafts).sort(
    (a, b) => b.updatedAt - a.updatedAt,
  )) {
    const server = byId.get(draft.data.systemId);
    if (!server || server.status === "armed") continue;
    kept.add(draft.data.systemId);
    entries.push({ origin: "draft", draft });
  }
  for (const system of systems) {
    if (DEMO_SYSTEM_IDS.has(system.system_id)) continue;
    if (system.status === "armed") continue;
    if (kept.has(system.system_id)) continue;
    entries.push({ origin: "server", system });
  }
  return entries;
}
