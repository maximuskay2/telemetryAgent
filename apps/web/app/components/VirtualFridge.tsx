"use client";

export type FridgeState = {
  temp_c: number;
  current_a: number;
  vibration_g: number;
  door_open: boolean;
  compressor_on: boolean;
  condenser_dirty: boolean;
  surge_active: boolean;
  short_cycling: boolean;
  defrost_active?: boolean;
};

const FAULTS: Array<{ label: string; value: string }> = [
  { label: "Open door", value: "door_open" },
  { label: "Dirty condenser", value: "condenser_fouling" },
  { label: "Power surge", value: "power_surge" },
  { label: "Rapid restart", value: "rapid_restart" },
  { label: "Defrost stuck", value: "defrost_stuck" },
];

const ACTIONS: Array<{ label: string; value: string }> = [
  { label: "Close door", value: "close_door" },
  { label: "Clean condenser", value: "clean_condenser" },
  { label: "End defrost", value: "end_defrost" },
  { label: "Reset", value: "reset" },
];

const BEHAVIOURS: Array<{ label: string; value: string }> = [
  { label: "Defrost", value: "defrost" },
  { label: "Restock (door 1 min)", value: "restock" },
];

function Gauge({
  label,
  value,
  unit,
  max,
  warnAt,
}: {
  label: string;
  value: number;
  unit: string;
  max: number;
  warnAt: number;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const hot = value > warnAt;
  return (
    <div className="gauge">
      <div className="gauge-head">
        <span>{label}</span>
        <span className={hot ? "gauge-val hot" : "gauge-val"}>
          {value.toFixed(value < 1 ? 3 : 1)} {unit}
        </span>
      </div>
      <div className="gauge-track">
        <div
          className={hot ? "gauge-fill hot" : "gauge-fill"}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function TempChart({ temps, warnTemp }: { temps: number[]; warnTemp: number }) {
  const W = 260;
  const H = 80;
  const MAX = 10;
  const y = (t: number) => H - 6 - (Math.max(0, Math.min(MAX, t)) / MAX) * (H - 12);
  const points =
    temps.length > 1
      ? temps
          .map((t, i) => `${((i / (temps.length - 1)) * (W - 4) + 2).toFixed(1)},${y(t).toFixed(1)}`)
          .join(" ")
      : "";
  return (
    <svg className="temp-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Temperature history">
      <line x1="0" x2={W} y1={y(warnTemp)} y2={y(warnTemp)} className="warn-line" />
      <text x={W - 4} y={y(warnTemp) - 4} className="warn-tag">
        warn {warnTemp}°C
      </text>
      {points ? <polyline points={points} className="temp-line" /> : null}
    </svg>
  );
}

export default function VirtualFridge({
  temps,
  state,
  warnTemp = 5,
  onFault,
  onAction,
  onBehaviour,
}: {
  temps: number[];
  state: FridgeState | null;
  warnTemp?: number;
  onFault: (fault: string) => void;
  onAction: (action: string) => void;
  onBehaviour: (behaviour: string) => void;
}) {
  const s: FridgeState = state ?? {
    temp_c: 0,
    current_a: 0,
    vibration_g: 0,
    door_open: false,
    compressor_on: false,
    condenser_dirty: false,
    surge_active: false,
    short_cycling: false,
  };
  return (
    <div className="fridge-wrap">
      <svg className="fridge" viewBox="0 0 220 260" role="img" aria-label="Virtual fridge">
        <rect x="60" y="20" width="110" height="220" rx="8" className="fridge-cavity" />
        <rect x="70" y="30" width="26" height="8" rx="4" className={s.door_open ? "fridge-light on" : "fridge-light"} />
        <line x1="70" y1="100" x2="160" y2="100" className="fridge-shelf" />
        <line x1="70" y1="150" x2="160" y2="150" className="fridge-shelf" />
        <rect
          x="132"
          y="196"
          width="28"
          height="28"
          rx="4"
          className={
            "fridge-compressor" +
            (s.compressor_on ? " on" : "") +
            (s.short_cycling ? " cycling" : "")
          }
        />
        {s.condenser_dirty ? (
          <g className="fridge-frost">
            <circle cx="72" cy="180" r="7" />
            <circle cx="82" cy="188" r="5" />
            <circle cx="70" cy="196" r="4" />
          </g>
        ) : null}
        <g
          className="fridge-door"
          style={{
            transform: s.door_open ? "rotate(-38deg)" : "rotate(0deg)",
            transformOrigin: "60px 20px",
          }}
        >
          <rect x="60" y="20" width="110" height="220" rx="8" className="fridge-door-panel" />
          <rect x="156" y="90" width="6" height="46" rx="3" className="fridge-handle" />
          <text x="96" y="145" className="fridge-brand">
            °C
          </text>
        </g>
        {s.surge_active ? <rect x="60" y="20" width="110" height="220" rx="8" className="fridge-surge" /> : null}
        {s.defrost_active ? (
          <text x="115" y="40" className="fridge-badge">
            DEFROST
          </text>
        ) : null}
        <text x="115" y="256" className="fridge-temp">
          {state ? `${s.temp_c.toFixed(1)}°C` : "—"}
        </text>
      </svg>
      <div className="fridge-side">
        <Gauge label="Temperature" value={s.temp_c} unit="°C" max={10} warnAt={warnTemp} />
        <Gauge label="Current" value={s.current_a} unit="A" max={6} warnAt={1.43} />
        <Gauge label="Vibration" value={s.vibration_g} unit="g" max={0.25} warnAt={0.1} />
        <TempChart temps={temps} warnTemp={warnTemp} />
        <div className="fridge-btns" role="group" aria-label="Fault injection">
          {FAULTS.map((f) => (
            <button key={f.value} type="button" onClick={() => onFault(f.value)}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="fridge-btns" role="group" aria-label="Technician actions">
          {ACTIONS.map((a) => (
            <button
              key={a.value}
              type="button"
              className="ghost"
              onClick={() => onAction(a.value)}
            >
              {a.label}
            </button>
          ))}
        </div>
        <div className="fridge-btns" role="group" aria-label="Normal behaviours">
          {BEHAVIOURS.map((b) => (
            <button key={b.value} type="button" onClick={() => onBehaviour(b.value)}>
              {b.label}
            </button>
          ))}
        </div>
        {!state ? <p className="mapempty">Click a fault to start the stream.</p> : null}
      </div>
    </div>
  );
}
