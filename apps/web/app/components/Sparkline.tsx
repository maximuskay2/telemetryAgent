const SPARK_POINTS = 40;

export default function Sparkline({
  values,
  label = "Error rate",
}: {
  values: number[];
  label?: string;
}) {
  if (values.length < 2) return <span className="hint">waiting for metrics…</span>;
  const recent = values.slice(-SPARK_POINTS);
  const max = Math.max(0.05, ...recent);
  const step = 100 / (SPARK_POINTS - 1);
  const points = recent
    .map((v, i) => `${(i * step).toFixed(1)},${(28 - (v / max) * 26).toFixed(1)}`)
    .join(" ");
  return (
    <svg className="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-label={label}>
      <polyline points={points} />
    </svg>
  );
}
