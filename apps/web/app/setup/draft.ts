// Incomplete /setup runs stay resumable drafts (per system) so a
// reload or a failed step never forces starting over. Mirrors
// connect/draft.ts; the mission gate lists both side by side.
export type SetupDraftData = {
  systemId: string;
  step: string;
  name: string;
  kind: string;
};

export type SetupDraft = {
  data: SetupDraftData;
  updatedAt: number;
};

export type SetupDraftMap = Record<string, SetupDraft>;

type StringStore = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

const DRAFT_KEY = "ta_setup_drafts";

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

export function loadSetupDrafts(store?: StringStore | null): SetupDraftMap {
  const storage = store === undefined ? webStore() : store;
  if (!storage) return {};
  try {
    const raw = storage.getItem(DRAFT_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed as SetupDraftMap;
  } catch {
    return {};
  }
}

function writeSetupDrafts(
  drafts: SetupDraftMap,
  store?: StringStore | null,
): void {
  const storage = store === undefined ? webStore() : store;
  if (!storage) return;
  try {
    storage.setItem(DRAFT_KEY, JSON.stringify(drafts));
  } catch {
    // storage full/blocked: drafts are best-effort
  }
}

export function saveSetupDraft(
  data: SetupDraftData,
  store?: StringStore | null,
): void {
  if (!data.systemId) return;
  const drafts = loadSetupDrafts(store);
  drafts[data.systemId] = { data, updatedAt: Date.now() };
  writeSetupDrafts(drafts, store);
}

/** Human step names for draft lists (mirrors /setup's stepper). */
export const STEP_LABELS: Record<string, string> = {
  connect: "Meet the business",
  teach: "Read the manuals",
  review: "Check what it learned",
  learn: "Watch normal",
  policy: "Permissions",
  arm: "Start watching",
};

export function clearSetupDraft(
  systemId: string,
  store?: StringStore | null,
): void {
  const drafts = loadSetupDrafts(store);
  if (!(systemId in drafts)) return;
  delete drafts[systemId];
  writeSetupDrafts(drafts, store);
}
