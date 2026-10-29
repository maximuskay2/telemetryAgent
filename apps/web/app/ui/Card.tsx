import type { ReactNode } from "react";

export default function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-[10px] border border-border bg-surface shadow-[0_8px_30px_rgb(0,0,0/0.35),inset_0_1px_0_0_rgb(255,255,255/0.04)] ${className}`}
    >
      {title !== undefined && (
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <h3 className="text-[13px] font-medium text-text">{title}</h3>
          {action}
        </header>
      )}
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}
