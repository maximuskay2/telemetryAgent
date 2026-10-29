import type { ButtonHTMLAttributes, ReactNode } from "react";

const TONES: Record<string, string> = {
  primary:
    "bg-brand text-[#0b1710] hover:bg-brand/90 focus-visible:ring-brand disabled:bg-brand/40",
  secondary:
    "border border-border bg-surface-2 text-text hover:bg-surface-2/70 focus-visible:ring-brand disabled:opacity-50",
  danger:
    "bg-crit text-[#0b1710] hover:bg-crit/90 focus-visible:ring-crit disabled:bg-crit/40",
  ghost: "text-text-muted hover:bg-surface-2 hover:text-text focus-visible:ring-brand disabled:opacity-50",
};

export default function Button({
  tone = "secondary",
  className = "",
  children,
  ...rest
}: {
  tone?: "primary" | "secondary" | "danger" | "ghost";
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:cursor-not-allowed ${TONES[tone]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function StatusDot({
  tone,
  pulse = false,
  label,
}: {
  tone: "ok" | "warn" | "crit" | "brand" | "neutral";
  pulse?: boolean;
  label?: string;
}) {
  const dot: Record<string, string> = {
    ok: "bg-ok",
    warn: "bg-warn",
    crit: "bg-crit",
    brand: "bg-brand",
    neutral: "bg-text-faint",
  };
  return (
    <span className="inline-flex items-center gap-1.5" title={label}>
      <span className="relative flex size-2">
        {pulse && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 motion-reduce:hidden ${dot[tone]}`}
          />
        )}
        <span className={`relative inline-flex size-2 rounded-full ${dot[tone]}`} />
      </span>
      {label && <span className="text-xs text-text-muted">{label}</span>}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-block rounded-md border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-text-muted">
      {children}
    </kbd>
  );
}
