/** Guided-demo step sync: which step is live, per demo track. Pure logic. */

export type DemoTrack = "shop" | "freezer";

export const TRACK_DOMAIN: Record<DemoTrack, string> = {
  shop: "software",
  freezer: "appliance",
};

export const TRACK_NAME: Record<DemoTrack, string> = {
  shop: "Shop",
  freezer: "Freezer",
};

/** Pipeline milestones seen on the socket for one track. */
export type StepMarks = {
  triggered: boolean;
  diagnosed: boolean;
  verified: boolean;
  resolved: boolean;
};

export const EMPTY_MARKS: StepMarks = {
  triggered: false,
  diagnosed: false,
  verified: false,
  resolved: false,
};

/**
 * Furthest step the demo has actually reached (1-5). Marks only count in
 * pipeline order, so an out-of-order event can never skip a step ahead.
 */
export function maxReadyStep(marks: StepMarks): number {
  if (!marks.triggered) return 1;
  if (!marks.diagnosed) return 2;
  if (!marks.verified) return 3;
  if (!marks.resolved) return 4;
  return 5;
}

/** Socket event domain -> demo track, or null when the event is not demo work. */
export function trackOfDomain(domain: unknown): DemoTrack | null {
  if (domain === TRACK_DOMAIN.shop) return "shop";
  if (domain === TRACK_DOMAIN.freezer) return "freezer";
  return null;
}

/** Live panel each step points at. Trace and veto are shared; ends are per demo. */
export function stepTarget(step: number, track: DemoTrack): string {
  if (step === 2 || step === 3) return "tour-trace";
  if (step === 4) return "tour-veto";
  return track === "shop" ? "tour-shop" : "tour-freezer";
}

export const STEP_LABELS: Record<
  DemoTrack,
  readonly [string, string, string, string, string]
> = {
  shop: [
    "Break the shop",
    "Watch it diagnose",
    "Watch it prove the fix",
    "The cancel window",
    "Fixed — try the freezer",
  ],
  freezer: [
    "Open the freezer door",
    "Watch it diagnose",
    "Watch it prove the fix",
    "The cancel window",
    "Fixed — try the shop",
  ],
};
