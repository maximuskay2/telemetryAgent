export function Sparkline({
  points,
  stroke = "currentColor",
  width = 120,
  height = 28,
  markerAt,
}: {
  points: number[];
  stroke?: string;
  width?: number;
  height?: number;
  /** Index into points where a vertical marker line is drawn. */
  markerAt?: number;
}) {
  if (points.length < 2) return <svg width={width} height={height} aria-hidden />;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - 2 - ((p - min) / span) * (height - 4)).toFixed(1)}`,
    )
    .join(" ");
  const markerX =
    markerAt !== undefined && markerAt >= 0 && markerAt < points.length
      ? markerAt * step
      : null;
  return (
    <svg width={width} height={height} aria-hidden className="block">
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" />
      {markerX !== null && (
        <line x1={markerX} y1={0} x2={markerX} y2={height} stroke="var(--ok)" strokeWidth={1.5} />
      )}
    </svg>
  );
}

export default function Metric({
  label,
  value,
  unit,
  delta,
  points,
  tone = "text",
  markerAt,
}: {
  label: string;
  value: string;
  unit?: string;
  delta?: string;
  points?: number[];
  tone?: "text" | "ok" | "warn" | "crit" | "brand";
  markerAt?: number;
}) {
  const tones: Record<string, string> = {
    text: "text-text",
    ok: "text-ok",
    warn: "text-warn",
    crit: "text-crit",
    brand: "text-brand-cyan",
  };
  return (
    <div className="min-w-0">
      <p className="truncate text-xs text-text-muted">{label}</p>
      <p className={`font-mono text-xl tabular-nums ${tones[tone]}`}>
        {value}
        {unit && <span className="ml-1 text-xs text-text-faint">{unit}</span>}
      </p>
      <div className="mt-0.5 flex items-end justify-between gap-2">
        {delta ? (
          <span className="text-xs text-text-faint">{delta}</span>
        ) : (
          <span />
        )}
        {points && points.length > 1 && (
          <Sparkline points={points} markerAt={markerAt} />
        )}
      </div>
    </div>
  );
}
