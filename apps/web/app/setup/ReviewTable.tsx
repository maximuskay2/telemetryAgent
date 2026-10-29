import { Button, Card, EmptyState } from "../ui";
import type { SetupProfile } from "../lib/setupApi";

export type ReviewField = { key: string; label: string; type?: string };

export type ReviewProvenance = {
  source_doc?: string;
  page_or_region?: string;
  quote?: string;
  confidence?: number;
  confirmed_by?: string;
  confirmed_at?: string;
};

function ProvenanceLine({ row }: { row: Record<string, unknown> }) {
  const provenance = (row.provenance ?? {}) as ReviewProvenance;
  return (
    <p className="mt-1.5 text-xs text-text-faint">
      {provenance.source_doc ?? "manual"}
      {provenance.page_or_region ? ` · ${provenance.page_or_region}` : ""}
      {provenance.quote ? ` — “${provenance.quote}”` : ""}
      {provenance.confirmed_by ? ` ✓ ${provenance.confirmed_by}` : ""}
    </p>
  );
}

/** One profile row: editable inputs in /setup, plain text in the journey. */
export function EntryCard({
  row,
  fields,
  onCell,
  onRemove,
}: {
  row: Record<string, unknown>;
  fields: ReviewField[];
  onCell?: (key: string, raw: string, type?: string) => void;
  onRemove?: () => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface-2/50 p-2.5">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {fields.map((field) =>
          onCell ? (
            <label key={field.key} className="flex min-w-0 flex-col gap-1">
              <span className="text-xs text-text-muted">{field.label}</span>
              <input
                type={field.type ?? "text"}
                value={String(row[field.key] ?? "")}
                onChange={(event) =>
                  onCell(field.key, event.target.value, field.type)
                }
                className="w-full rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-sm text-text outline-none placeholder:text-text-faint focus:border-brand"
              />
            </label>
          ) : (
            <div key={field.key} className="flex min-w-0 flex-col gap-1">
              <span className="text-xs text-text-muted">{field.label}</span>
              <span className="text-sm text-text">
                {String(row[field.key] ?? "—")}
              </span>
            </div>
          ),
        )}
      </div>
      <ProvenanceLine row={row} />
      {onRemove && (
        <div className="mt-1.5">
          <Button tone="ghost" onClick={onRemove}>
            Remove
          </Button>
        </div>
      )}
    </div>
  );
}

export function ReviewSection({
  title,
  rows,
  fields,
  onChange,
}: {
  title: string;
  rows: Record<string, unknown>[];
  fields: ReviewField[];
  onChange?: (rows: Record<string, unknown>[]) => void;
}) {
  return (
    <Card
      title={title}
      action={
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[11px] tabular-nums text-text-muted">
          {rows.length}
        </span>
      }
    >
      <div className="flex flex-col gap-2">
        {rows.length === 0 && (
          <EmptyState
            title="None yet"
            hint={onChange ? "Add a row below." : "Nothing learned here."}
          />
        )}
        {rows.map((row, i) => (
          <EntryCard
            key={i}
            row={row}
            fields={fields}
            onCell={
              onChange
                ? (key, raw, type) => {
                    const value = type === "number" ? Number(raw) : raw;
                    onChange(
                      rows.map((r, j) =>
                        j === i ? { ...r, [key]: value } : r,
                      ),
                    );
                  }
                : undefined
            }
            onRemove={
              onChange
                ? () => onChange(rows.filter((_, j) => j !== i))
                : undefined
            }
          />
        ))}
        {onChange && (
          <div>
            <Button
              tone="ghost"
              onClick={() => {
                const blank: Record<string, unknown> = {
                  provenance: { source_doc: "manual" },
                };
                for (const field of fields) {
                  blank[field.key] = field.type === "number" ? 0 : "";
                }
                onChange([...rows, blank]);
              }}
            >
              + Add row
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}

const SECTION_FIELDS: Record<string, ReviewField[]> = {
  normal_ranges: [
    { key: "metric", label: "Metric" },
    { key: "min", label: "Min", type: "number" },
    { key: "max", label: "Max", type: "number" },
    { key: "unit", label: "Unit" },
  ],
  expected_behaviours: [
    { key: "name", label: "Name" },
    { key: "signature", label: "Signature" },
    { key: "schedule", label: "Schedule" },
    { key: "max_duration_s", label: "Max s", type: "number" },
    { key: "allowed_effect", label: "Allowed effect" },
  ],
  modes: [
    { key: "mode", label: "Mode" },
    { key: "max_duration_s", label: "Max s", type: "number" },
  ],
  failure_definitions: [
    { key: "name", label: "Name" },
    { key: "metric", label: "Metric" },
    { key: "op", label: "Op" },
    { key: "threshold", label: "Threshold", type: "number" },
    { key: "duration_s", label: "For s", type: "number" },
  ],
  hard_limits: [
    { key: "metric", label: "Metric" },
    { key: "op", label: "Op" },
    { key: "threshold", label: "Threshold", type: "number" },
  ],
};

const SECTION_TITLES: Record<string, string> = {
  normal_ranges: "Normal ranges",
  expected_behaviours: "Expected behaviours",
  modes: "Modes",
  failure_definitions: "Failure definitions",
  hard_limits: "Hard limits (never suppressible)",
};

/** Read-only full review table for the journey's "see everything" view. */
export function ReviewTables({ profile }: { profile: SetupProfile }) {
  return (
    <div className="flex flex-col gap-2">
      {Object.keys(SECTION_TITLES).map((section) => (
        <ReviewSection
          key={section}
          title={SECTION_TITLES[section]}
          rows={
            (profile[section as keyof SetupProfile] as Record<
              string,
              unknown
            >[]) ?? []
          }
          fields={SECTION_FIELDS[section]}
        />
      ))}
    </div>
  );
}
