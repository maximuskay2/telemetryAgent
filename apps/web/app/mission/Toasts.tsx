"use client";

import { useEffect } from "react";
import { useMission, type Toast } from "./state";

const TONES: Record<Toast["tone"], string> = {
  info: "border-brand-cyan/50 text-text",
  ok: "border-ok/50 text-text",
  subtle: "border-border text-text-muted",
};

function ToastRow({ toast }: { toast: Toast }) {
  const { dismissToast } = useMission();
  useEffect(() => {
    const timer = window.setTimeout(
      () => dismissToast(toast.id),
      toast.tone === "subtle" ? 3500 : 6000,
    );
    return () => window.clearTimeout(timer);
  }, [toast.id, toast.tone, dismissToast]);
  return (
    <div
      role="status"
      className={`flex items-center gap-2 rounded-lg border bg-surface-2 px-3 py-2 text-xs shadow-lg ${TONES[toast.tone]}`}
    >
      <span className="flex-1">{toast.text}</span>
      <button
        type="button"
        aria-label="Dismiss"
        title="Dismiss"
        onClick={() => dismissToast(toast.id)}
        className="text-text-faint hover:text-text"
      >
        ✕
      </button>
    </div>
  );
}

export default function Toasts() {
  const { toasts } = useMission();
  if (toasts.length === 0) return null;
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-3 bottom-12 z-50 flex w-72 flex-col gap-2"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastRow toast={toast} />
        </div>
      ))}
    </div>
  );
}
