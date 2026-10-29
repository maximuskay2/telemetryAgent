import type { LucideIcon } from "lucide-react";
import { Inbox, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import Button from "./Button";

function Shell({
  icon: Icon,
  tone,
  title,
  hint,
  children,
}: {
  icon: LucideIcon;
  tone: string;
  title: string;
  hint?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-4 py-8 text-center">
      <Icon size={22} className={tone} aria-hidden />
      <p className="text-sm font-medium text-text">{title}</p>
      {hint && <p className="max-w-xs text-xs text-text-muted">{hint}</p>}
      {children}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <Shell icon={Inbox} tone="text-text-faint" title={title} hint={hint}>
      {action}
    </Shell>
  );
}

export function ErrorState({
  title,
  hint,
  onRetry,
}: {
  title: string;
  hint?: string;
  onRetry?: () => void;
}) {
  return (
    <Shell icon={TriangleAlert} tone="text-warn" title={title} hint={hint}>
      {onRetry && (
        <Button tone="secondary" onClick={onRetry} className="mt-2">
          Retry
        </Button>
      )}
    </Shell>
  );
}
