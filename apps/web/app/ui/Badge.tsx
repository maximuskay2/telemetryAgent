import {
  Ban,
  Check,
  Eye,
  OctagonAlert,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

export type Tone = "ok" | "warn" | "crit" | "brand" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  ok: "border-ok/40 bg-ok/10 text-ok",
  warn: "border-warn/40 bg-warn/10 text-warn",
  crit: "border-crit/40 bg-crit/10 text-crit",
  brand: "border-brand/40 bg-brand/10 text-brand-cyan",
  neutral: "border-border bg-surface-2 text-text-muted",
};

/** Status vocabulary from §3: every status is colour + icon + word. */
export type StatusPreset =
  | "healthy"
  | "ignored"
  | "observing"
  | "incident"
  | "hardLimit"
  | "ai"
  | "learning"
  | "setup";

export const STATUS: Record<StatusPreset, { tone: Tone; icon: LucideIcon; word: string }> = {
  healthy: { tone: "ok", icon: Check, word: "Healthy" },
  ignored: { tone: "ok", icon: ShieldCheck, word: "Normal · ignored" },
  observing: { tone: "warn", icon: Eye, word: "Observing" },
  incident: { tone: "crit", icon: OctagonAlert, word: "Incident" },
  hardLimit: { tone: "crit", icon: Ban, word: "Hard limit" },
  ai: { tone: "brand", icon: Sparkles, word: "Agent" },
  learning: { tone: "brand", icon: RefreshCw, word: "Learning" },
  setup: { tone: "warn", icon: Settings, word: "Setup needed" },
};

export default function Badge({
  tone,
  icon,
  children,
  title,
}: {
  tone: Tone;
  icon?: ReactNode;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${TONE_CLASSES[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}

export function StatusBadge({
  preset,
  label,
}: {
  preset: StatusPreset;
  label?: string;
}) {
  const { tone, icon: Icon, word } = STATUS[preset];
  return (
    <Badge tone={tone} icon={<Icon size={12} strokeWidth={2.5} />}>
      {label ?? word}
    </Badge>
  );
}
