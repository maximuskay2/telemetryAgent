import type { ReactNode } from "react";

export default function Tooltip({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 hidden -translate-x-1/2 rounded-lg border border-border bg-surface-2 px-2 py-1 text-xs whitespace-nowrap text-text shadow-lg group-hover:block"
      >
        {label}
      </span>
    </span>
  );
}
