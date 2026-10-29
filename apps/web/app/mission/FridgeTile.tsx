"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../lib/api";
import { useMission } from "./state";
import TileStatus from "./TileStatus";

const FAULTS = [
  { value: "door_open", label: "Door left open" },
  { value: "condenser_fouling", label: "Dirty condenser" },
  { value: "power_surge", label: "Voltage surge" },
  { value: "rapid_restart", label: "Rapid restart" },
  { value: "defrost_stuck", label: "Defrost stuck" },
];

const FIXES = [
  { value: "close_door", label: "Close door" },
  { value: "clean_condenser", label: "Clean condenser" },
  { value: "end_defrost", label: "End defrost" },
  { value: "reset", label: "Reset controller" },
];

function isTempMetric(metric: unknown): boolean {
  return metric === "temp_c" || metric === "temperature_c";
}

/** Normal band from the profile: normal_ranges first, hard limits as a net. */
function normalTempBand(body: unknown): { min: number; max: number } | null {
  if (typeof body !== "object" || body === null) return null;
  const profile = (body as { profile?: unknown }).profile ?? body;
  if (typeof profile !== "object" || profile === null) return null;
  const ranges = (profile as { normal_ranges?: unknown }).normal_ranges;
  if (Array.isArray(ranges)) {
    for (const row of ranges) {
      if (typeof row !== "object" || row === null) continue;
      const { metric, min, max } = row as {
        metric?: unknown;
        min?: unknown;
        max?: unknown;
      };
      if (isTempMetric(metric) && typeof min === "number" && typeof max === "number") {
        return { min, max };
      }
    }
  }
  const limits = (profile as { hard_limits?: unknown }).hard_limits;
  if (!Array.isArray(limits)) return null;
  // Hard limits mark the forbidden side: an upper violation caps normal.
  let min = 2;
  let max = 8;
  let found = false;
  for (const row of limits) {
    if (typeof row !== "object" || row === null) continue;
    const { metric, op, threshold, value } = row as {
      metric?: unknown;
      op?: unknown;
      threshold?: unknown;
      value?: unknown;
    };
    const limit = typeof threshold === "number" ? threshold : value;
    if (!isTempMetric(metric) || typeof limit !== "number") continue;
    if (op === "gt" || op === ">" || op === ">=") {
      max = Math.min(max, limit);
      found = true;
    } else if (op === "lt" || op === "<" || op === "<=") {
      min = Math.max(min, limit);
      found = true;
    }
  }
  return found ? { min, max } : null;
}

function TempCurve({
  temps,
  defrost,
  band,
  fixedAt,
}: {
  temps: number[];
  defrost: boolean[];
  band: { min: number; max: number } | null;
  fixedAt: number | null;
}) {
  if (temps.length < 2) {
    return <p className="text-xs text-text-faint">Waiting for fridge readings…</p>;
  }
  const W = 320;
  const H = 96;
  const lo = Math.min(...temps, band ? band.min : Infinity);
  const hi = Math.max(...temps, band ? band.max : -Infinity);
  const span = hi - lo || 1;
  const y = (t: number) => H - 4 - ((t - lo) / span) * (H - 8);
  const step = W / (temps.length - 1);
  const points = temps.map((t, i) => `${(i * step).toFixed(1)},${y(t).toFixed(1)}`).join(" ");
  const bandTop = band ? y(band.max) : 0;
  const bandBottom = band ? y(band.min) : 0;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Fridge temperature">
      {band && (
        <rect
          x={0}
          y={bandTop}
          width={W}
          height={Math.max(2, bandBottom - bandTop)}
          className="fill-ok/10"
        />
      )}
      {defrost.map((active, i) =>
        active ? (
          <rect
            key={i}
            x={i * step}
            y={0}
            width={step + 1}
            height={H}
            className="fill-brand-cyan/10"
          />
        ) : null,
      )}
      <polyline
        points={points}
        fill="none"
        strokeWidth={1.5}
        className="stroke-brand-cyan"
        strokeLinejoin="round"
      />
      {fixedAt !== null && (
        <line x1={W - 1} y1={0} x2={W - 1} y2={H} className="stroke-ok" strokeWidth={1.5} />
      )}
    </svg>
  );
}

export default function FridgeTile({ systemId }: { systemId: string | null }) {
  const { fridgeTemps, fridgeDefrost, fridge, fridgeControl, fridgeBehaviour, events } =
    useMission();
  const [band, setBand] = useState<{ min: number; max: number } | null>(null);
  const [menu, setMenu] = useState<"faults" | "fixes" | null>(null);
  const [fixedAt, setFixedAt] = useState<number | null>(null);
  const [ambientHot, setAmbientHot] = useState(false);

  useEffect(() => {
    if (!systemId) return;
    let cancelled = false;
    fetch(`${apiUrl}/api/systems/${encodeURIComponent(systemId)}/profile`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body: unknown) => {
        if (!cancelled) setBand(normalTempBand(body));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [systemId]);

  useEffect(() => {
    const applied = events.find(
      (e) => e.source === "fix" && e.message.includes("fridge"),
    );
    if (applied) setFixedAt(Date.now());
  }, [events]);

  const temp = fridge?.temp_c;
  const amps = fridge?.current_a;
  const vib = fridge?.vibration_g;

  return (
    <section aria-label="Cold chain freezer" className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-text">Cold chain freezer</h2>
        <TileStatus domain="appliance" systemId={systemId} />
      </div>

      <div className="mt-3 grid grid-cols-[auto_1fr] items-center gap-3">
        <svg viewBox="0 0 64 96" className="h-24" role="img" aria-label="Freezer">
          <rect x="8" y="4" width="48" height="88" rx="6" className="fill-surface-2 stroke-border" />
          <line x1="8" y1="38" x2="56" y2="38" className="stroke-border" />
          <line x1="48" y1="12" x2="48" y2="30" className="stroke-text-faint" strokeWidth={2} />
          <line x1="48" y1="46" x2="48" y2="64" className="stroke-text-faint" strokeWidth={2} />
          {fridge?.door_open && (
            <rect x="8" y="4" width="10" height="88" className="fill-warn/30" />
          )}
          {fridge?.condenser_dirty && (
            <circle cx="32" cy="78" r="6" className="fill-crit/40" />
          )}
        </svg>
        <dl className="grid grid-cols-3 gap-2 text-center">
          {[
            { label: "Temp", value: typeof temp === "number" ? `${temp.toFixed(1)}°C` : "—" },
            { label: "Current", value: typeof amps === "number" ? `${amps.toFixed(2)}A` : "—" },
            { label: "Vibration", value: typeof vib === "number" ? `${vib.toFixed(2)}g` : "—" },
          ].map((g) => (
            <div key={g.label} className="rounded-md border border-border bg-surface-2 px-1 py-2">
              <dt className="text-[11px] text-text-faint">{g.label}</dt>
              <dd className="text-sm font-semibold text-text tabular-nums">{g.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="mt-3">
        <TempCurve temps={fridgeTemps} defrost={fridgeDefrost} band={band} fixedAt={fixedAt} />
        <div className="mt-1 flex items-center gap-3 text-[11px] text-text-faint">
          <span>
            <span className="mr-1 inline-block h-2 w-3 rounded-sm bg-ok/30" />
            {band ? `normal ${band.min.toFixed(0)}–${band.max.toFixed(0)}°C` : "normal band"}
          </span>
          <span>
            <span className="mr-1 inline-block h-2 w-3 rounded-sm bg-brand-cyan/30" />
            defrost
          </span>
          {fridge && (
            <span className="ml-auto">
              {fridge.defrost_active
                ? "Defrosting"
                : fridge.compressor_on
                  ? "Cooling"
                  : "Idle"}
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => fridgeBehaviour("restock")}
          className="rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint"
        >
          Restock
        </button>
        <button
          type="button"
          onClick={() => fridgeBehaviour("defrost")}
          className="rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint"
        >
          Defrost
        </button>
        <button
          type="button"
          aria-pressed={ambientHot}
          onClick={() => {
            fridgeBehaviour("ambient", { hot: !ambientHot });
            setAmbientHot(!ambientHot);
          }}
          className="rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint"
        >
          Ambient {ambientHot ? "on" : "off"}
        </button>
        <div className="relative ml-auto flex gap-2">
          <button
            type="button"
            aria-expanded={menu === "faults"}
            onClick={() => setMenu(menu === "faults" ? null : "faults")}
            className="rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint"
          >
            Faults ▾
          </button>
          <button
            type="button"
            aria-expanded={menu === "fixes"}
            onClick={() => setMenu(menu === "fixes" ? null : "fixes")}
            className="rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint"
          >
            Fix ▾
          </button>
          {menu && (
            <div
              role="menu"
              className="absolute right-0 top-full z-10 mt-1 w-48 rounded-md border border-border bg-surface-2 py-1 shadow-lg"
            >
              {(menu === "faults" ? FAULTS : FIXES).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    if (menu === "faults") fridgeControl("fault", { fault: opt.value });
                    else fridgeControl("action", { action: opt.value });
                    setMenu(null);
                  }}
                  className="block w-full px-3 py-1.5 text-left text-xs text-text hover:bg-surface"
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
