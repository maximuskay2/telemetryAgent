"use client";

export type LaneState = "done" | "active" | "todo" | "failed";

export default function PipelineLane({
  labels,
  reached,
  running,
  failed,
}: {
  labels: string[];
  reached: boolean[];
  running: boolean;
  failed: boolean;
}) {
  const last = reached.length - 1;
  const states: LaneState[] = reached.map((done, i) => {
    if (done) return failed && i === last ? "failed" : "done";
    const prevDone = i === 0 || reached[i - 1];
    if (prevDone && (running || failed)) return failed ? "failed" : "active";
    return "todo";
  });
  return (
    <ol className="lane" aria-label="Pipeline progress">
      {labels.map((label, i) => (
        <li
          key={label}
          className={`lstep ${states[i]}`}
          aria-current={states[i] === "active" ? "step" : undefined}
        >
          <span className="ldot">{i + 1}</span>
          <span className="llabel">{label}</span>
        </li>
      ))}
    </ol>
  );
}
