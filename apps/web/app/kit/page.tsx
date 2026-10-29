"use client";

import { notFound } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Kbd,
  Metric,
  Sheet,
  StatusBadge,
  StatusDot,
  Tabs,
  Tooltip,
} from "../ui";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card title={title}>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </Card>
  );
}

export default function KitPage() {
  const [tab, setTab] = useState("all");
  const [sheet, setSheet] = useState(false);
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <main className="min-h-screen bg-bg p-6 font-sans text-text">
      <h1 className="mb-1 text-xl font-semibold">Component kit</h1>
      <p className="mb-4 text-sm text-text-muted">
        Classic palette primitives. Hidden in production builds.
      </p>
      <div className="grid max-w-5xl grid-cols-1 gap-3 md:grid-cols-2">
        <Section title="Badges">
          <StatusBadge preset="healthy" />
          <StatusBadge preset="ignored" />
          <StatusBadge preset="observing" />
          <StatusBadge preset="incident" />
          <StatusBadge preset="hardLimit" />
          <StatusBadge preset="ai" label="Muse Spark" />
          <StatusBadge preset="learning" />
          <StatusBadge preset="setup" />
          <Badge tone="neutral">Neutral</Badge>
        </Section>
        <Section title="Buttons + dots + kbd">
          <Button tone="primary">Primary</Button>
          <Button tone="secondary">Secondary</Button>
          <Button tone="danger">Disapprove</Button>
          <Button tone="ghost">Ghost</Button>
          <StatusDot tone="ok" label="Live" pulse />
          <StatusDot tone="crit" label="Down" />
          <span>
            <Kbd>F</Kbd> <Kbd>P</Kbd>
          </span>
          <Tooltip label="Helpful hint">
            <Button tone="secondary">Hover me</Button>
          </Tooltip>
        </Section>
        <Section title="Tabs">
          <Tabs
            tabs={[
              { id: "all", label: "All", count: 15 },
              { id: "inc", label: "Incidents", count: 1 },
              { id: "ign", label: "Ignored", count: 14 },
            ]}
            active={tab}
            onChange={setTab}
          />
        </Section>
        <Section title="Metrics">
          <Metric label="Orders/min" value="32" delta="+4 vs 5m" points={[20, 24, 28, 31, 29, 33, 32]} />
          <Metric label="Error rate" value="12.0" unit="%" tone="crit" points={[1, 2, 4, 9, 12, 11, 12]} markerAt={4} />
        </Section>
        <Section title="States">
          <EmptyState title="No incidents" hint="Runs show up here as they happen." />
          <ErrorState title="Can't reach the agent API" hint="Start it first, then retry." onRetry={() => {}} />
        </Section>
        <Section title="Sheet">
          <Button tone="secondary" onClick={() => setSheet(true)}>
            Open drawer
          </Button>
          <Sheet open={sheet} onClose={() => setSheet(false)} title="Incident drawer">
            <p className="text-sm text-text-muted">Drawer content goes here.</p>
          </Sheet>
        </Section>
      </div>
    </main>
  );
}
