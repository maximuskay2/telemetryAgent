"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  APPLIANCE_STEP_TITLES,
  clearDraft,
  draftStepTitle,
  loadDrafts,
  SOFTWARE_STEP_TITLES,
  type DraftMap,
  type WizardDraft,
} from "../connect/draft";
import { signInHref } from "../lib/nextPath";
import { useSession } from "../lib/session";
import {
  clearSetupDraft,
  loadSetupDrafts,
  STEP_LABELS,
  type SetupDraft,
  type SetupDraftMap,
} from "../setup/draft";
import { Button, Card } from "../ui";

/**
 * Mission gate: Mission Control opens only once a system is armed and
 * watching. Until then this screen lists every unfinished setup —
 * guided (/connect) and manual (/setup) drafts side by side.
 */
export default function SetupSelect() {
  const router = useRouter();
  const { status } = useSession();
  const [guided, setGuided] = useState<DraftMap>(() => loadDrafts());
  const [manual, setManual] = useState<SetupDraftMap>(() =>
    loadSetupDrafts(),
  );
  const signedIn = status === "signed-in";

  // ?tour=1 with nothing armed still bounces to the guided setup.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("tour") === "1") {
      router.replace("/start/setup");
    }
  }, [router]);

  const guidedEntries = Object.values(guided).sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );
  const manualEntries = Object.values(manual).sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );

  function discardGuided(draft: WizardDraft) {
    clearDraft(draft.data.systemId);
    setGuided(loadDrafts());
  }

  function discardManual(draft: SetupDraft) {
    clearSetupDraft(draft.data.systemId);
    setManual(loadSetupDrafts());
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-3 p-4">
      <Card title="Set up a system to watch">
        <p className="text-sm text-text-muted">
          Mission Control opens once a system is armed and watching. Pick up
          a draft where it stopped, or start a setup.
        </p>
      </Card>

      {guidedEntries.length > 0 && (
        <Card title="Guided setup drafts">
          <ul className="flex flex-col gap-2">
            {guidedEntries.map((draft) => {
              const titles =
                draft.data.kind === "appliance"
                  ? APPLIANCE_STEP_TITLES
                  : SOFTWARE_STEP_TITLES;
              return (
                <li
                  key={draft.data.systemId}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-2 px-3 py-2"
                >
                  <span className="text-sm font-medium text-text">
                    {draft.data.name}
                  </span>
                  <span className="font-mono text-xs text-text-faint">
                    {draft.data.systemId}
                  </span>
                  <span className="text-xs text-text-muted">
                    · {draft.data.kind} · step {draft.index + 1} ·{" "}
                    {draftStepTitle(draft, titles)}
                  </span>
                  <span className="inline-flex gap-2">
                    <Link
                      href={`/connect?resume=${encodeURIComponent(draft.data.systemId)}`}
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      Continue
                    </Link>
                    <Button
                      tone="ghost"
                      onClick={() => discardGuided(draft)}
                    >
                      Discard
                    </Button>
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {manualEntries.length > 0 && (
        <Card title="Manual setup drafts">
          <ul className="flex flex-col gap-2">
            {manualEntries.map((draft) => (
              <li
                key={draft.data.systemId}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-2 px-3 py-2"
              >
                <span className="text-sm font-medium text-text">
                  {draft.data.name}
                </span>
                <span className="font-mono text-xs text-text-faint">
                  {draft.data.systemId}
                </span>
                <span className="text-xs text-text-muted">
                  · {draft.data.kind} ·{" "}
                  {STEP_LABELS[draft.data.step] ?? draft.data.step}
                </span>
                <span className="inline-flex gap-2">
                  <Link
                    href={`/setup?system=${encodeURIComponent(draft.data.systemId)}`}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    Continue
                  </Link>
                  <Button tone="ghost" onClick={() => discardManual(draft)}>
                    Discard
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Start new">
        <div className="flex flex-wrap gap-2">
          <Link
            href={signedIn ? "/connect" : signInHref("/connect")}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
          >
            Guided connect →
          </Link>
          <Link
            href={signedIn ? "/setup" : signInHref("/setup")}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
          >
            Manual setup
          </Link>
          {!signedIn && (
            <Link
              href="/start"
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-text outline-none hover:bg-surface-2/70 focus-visible:ring-2 focus-visible:ring-brand"
            >
              Try the live demo
            </Link>
          )}
        </div>
        {!signedIn && (
          <p className="mt-2 text-xs text-text-muted">
            Connecting real systems needs a sign-in. The demo needs none.
          </p>
        )}
      </Card>
    </main>
  );
}
