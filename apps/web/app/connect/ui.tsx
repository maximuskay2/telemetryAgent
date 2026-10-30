// Shared wizard atoms for /connect (N-R4).
"use client";

import { useState, type ReactNode } from "react";
import { Button, StatusDot } from "../ui";

export const inputCls =
  "mt-1 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text outline-none focus:border-brand disabled:opacity-50";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[13px] font-medium text-text">{label}</span>
      {children}
      {hint && (
        <span className="mt-1 block text-xs text-text-faint">{hint}</span>
      )}
    </label>
  );
}

export function CodeBlock({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (non-secure context); user selects manually.
    }
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface-2">
      <div className="flex items-center justify-between gap-2 px-3 py-1.5">
        <span className="text-xs text-text-faint">{label ?? "Run this"}</span>
        <button
          type="button"
          onClick={copy}
          className="cursor-pointer text-xs font-medium text-brand hover:underline"
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 pb-2.5 font-mono text-xs break-all whitespace-pre-wrap text-text">
        {text}
      </pre>
    </div>
  );
}

export function KeyOnce({ value }: { value: string | null }) {
  if (!value) {
    return (
      <p className="text-xs text-text-muted">
        The key was shown once. Rotate it in the connections panel for a new
        one.
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      <CodeBlock text={value} label="Secret key — copy it now" />
      <p className="text-xs font-medium text-warn">
        Shown once — it is never displayed again.
      </p>
    </div>
  );
}

export function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="text-[13px] text-crit">
      {message}
    </p>
  );
}

export function StepNav({
  onBack,
  onNext,
  nextLabel = "Continue",
  nextDisabled = false,
}: {
  onBack?: () => void;
  onNext: () => void;
  nextLabel?: string;
  nextDisabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 pt-1">
      {onBack && (
        <Button tone="ghost" onClick={onBack}>
          ← Back
        </Button>
      )}
      <Button tone="primary" onClick={onNext} disabled={nextDisabled}>
        {nextLabel}
      </Button>
    </div>
  );
}

export function WaitRow({
  waitingLabel,
  doneLabel,
  done,
  detail,
  live,
  onRecheck,
  onSkip,
  skipLabel = "Skip for now",
}: {
  waitingLabel: string;
  doneLabel: string;
  done: boolean;
  detail: string;
  live: boolean;
  onRecheck: () => void;
  onSkip: () => void;
  skipLabel?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border bg-surface-2 px-3 py-2.5">
      {done ? (
        <>
          <StatusDot tone="ok" label="received" />
          <span className="text-[13px] font-medium text-text">
            ✓ {doneLabel}
          </span>
          {detail && (
            <span className="text-xs text-text-faint">{detail}</span>
          )}
        </>
      ) : (
        <>
          <StatusDot tone="warn" pulse label="waiting" />
          <span className="text-[13px] text-text-muted">
            {waitingLabel}
            {!live && " (live socket down — polling on check)"}
          </span>
          <span className="inline-flex gap-2">
            <Button tone="ghost" onClick={onRecheck}>
              Check again
            </Button>
            <Button tone="ghost" onClick={onSkip}>
              {skipLabel}
            </Button>
          </span>
        </>
      )}
    </div>
  );
}
