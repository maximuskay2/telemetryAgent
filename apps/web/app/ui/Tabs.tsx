import type { KeyboardEvent } from "react";

export type Tab = { id: string; label: string; count?: number };

export default function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Tab[];
  active: string;
  onChange: (id: string) => void;
}) {
  function onKeyDown(event: KeyboardEvent, index: number) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = (index + delta + tabs.length) % tabs.length;
    onChange(tabs[next].id);
    const list = event.currentTarget.parentElement;
    const target = list?.querySelectorAll('[role="tab"]')[next] as HTMLElement | undefined;
    target?.focus();
  }

  return (
    <div role="tablist" aria-label="Filter" className="flex items-center gap-1">
      {tabs.map((tab, index) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-brand ${
              selected
                ? "bg-surface-2 text-text"
                : "text-text-muted hover:bg-surface-2/60 hover:text-text"
            }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className="rounded-full bg-bg px-1.5 text-[11px] tabular-nums">
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
