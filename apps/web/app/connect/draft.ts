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
