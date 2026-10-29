"use client";

import { useEffect, useState } from "react";
import type { IncidentEntry } from "../hooks/useIncidentList";
import { apiUrl, responseDetail } from "../lib/api";
import type { GateCheck, RunDetail, RunVerification } from "../types/api";
import { lineDiff } from "./lib/diff";
import { modelProvider } from "./lib/models";
import { useMission } from "./state";

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function strArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

function confidenceOf(text: string): number | null {
  const match = /confidence\s*[:=]?\s*(\d{1,3})\s*%/.exec(text);
  if (!match) return null;
  return Math.max(0, Math.min(100, Number(match[1])));
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="text-xs font-semibold tracking-wide text-text-faint uppercase">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

function VerifyBlock({ verification }: { verification: RunVerification }) {
  const original = verification.original;
  const patched = verification.patched;
  return (
    <div className="rounded-md border border-border bg-surface-2 p-2.5 text-xs">
      <p className="text-text">
        {original && !original.passed ? "✗ fails on original" : "· original"}{" "}
        <span aria-hidden>→</span>{" "}
        {patched && patched.passed ? "✓ passes on patch" : "· patch"}
      </p>
      {verification.runner && (
        <p className="mt-1 text-text-muted">runner: {verification.runner}</p>
      )}
      {original && (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-text-muted">original output</summary>
          <pre className="mt-1 max-h-32 overflow-auto font-mono text-[11px] whitespace-pre-wrap text-text-muted">
            {original.output.slice(0, 2000)}
          </pre>
        </details>
      )}
      {patched && (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-text-muted">patched output</summary>
          <pre className="mt-1 max-h-32 overflow-auto font-mono text-[11px] whitespace-pre-wrap text-text-muted">
            {patched.output.slice(0, 2000)}
          </pre>
        </details>
      )}
    </div>
  );
}

export default function IncidentDrawer({
  entry,
  onClose,
}: {
  entry: IncidentEntry;
  onClose: () => void;
}) {
  const { applyFix, applyRunbook, operatorToken, setTokenOpen } = useMission();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (entry.runId.startsWith("pending-")) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    fetch(`${apiUrl}/api/runs/${encodeURIComponent(entry.runId)}`)
      .then(async (response) => {
        if (response.status === 404) throw new Error("expired");
        if (!response.ok) throw new Error(await responseDetail(response));
        return (await response.json()) as RunDetail;
      })
      .then((body) => {
        if (!cancelled) {
          setDetail(body);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load run.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entry.runId]);

  const result = detail?.result ?? {};
  const status = str(result.status);
  const steps = detail?.steps ?? [];
  const attempts = steps.filter(
    (s) => s.step === "generate" || s.step === "verify",
  );
  const verifyMs = steps
    .filter((s) => s.step === "verify")
    .reduce((sum, s) => sum + (typeof s.duration_ms === "number" ? s.duration_ms : 0), 0);
  const confidence = confidenceOf(entry.diagnosis);
  const verification = ((result.verification ?? detail?.verification) ?? null) as RunVerification | null;
  const patch = str(result.patch_code);
  const original = verification?.original_code ?? "";
  const rows = patch && original ? lineDiff(original, patch) : [];
  const changed = rows.filter((r) => r.kind !== "same").length;
  const prUrl = str(result.pr_url);
  const runbookSteps = strArray(
    (result.runbook as { steps?: unknown } | undefined)?.steps,
  );
  const alert = (result.alert ?? {}) as {
    work_order_id?: unknown;
    work_order?: unknown;
    message?: unknown;
  };
  const gate = (detail?.gate ?? {}) as {
    decision?: unknown;
    reason?: unknown;
    rule?: unknown;
    fingerprint?: unknown;
    checks?: unknown;
  };
  const checks = Array.isArray(gate.checks)
    ? (gate.checks.filter((c): c is GateCheck => typeof c === "object" && c !== null) as GateCheck[])
    : [];
  const decision = detail?.decision;

  const apply = () => {
    if (!operatorToken) {
      setTokenOpen(true);
      return;
    }
    if (entry.domain === "software") applyFix(entry.runId);
    else applyRunbook(entry.runId);
  };

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Incident report">
      <button
        type="button"
        aria-label="Close report"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-black/60"
      />
      <div className="absolute top-0 right-0 flex h-full w-full max-w-xl flex-col overflow-y-auto border-l border-border bg-bg p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[11px] text-text-faint">
              {entry.domain === "software" ? "🛒 software" : "❄️ appliance"} ·{" "}
              {entry.runId.startsWith("pending-") ? "submitting…" : entry.runId}
            </p>
            <h2 className="mt-0.5 truncate text-base font-semibold text-text">
              {entry.diagnosis.split("\n")[0] || entry.telemetry.split("\n")[0] || "Incident"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md border border-border bg-surface-2 px-2.5 py-1 text-xs text-text hover:border-text-faint"
          >
            Close ✕
          </button>
        </div>

        <Section title="Diagnosis">
          {entry.diagnosis ? (
            <p className="text-sm whitespace-pre-wrap text-text">{entry.diagnosis}</p>
          ) : (
            <p className="text-sm text-text-faint">
              {entry.status === "running" ? "Diagnosing…" : "No diagnosis recorded."}
            </p>
          )}
          {confidence !== null && (
            <div className="mt-2">
              <div
                role="progressbar"
                aria-valuenow={confidence}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Diagnosis confidence"
                className="h-1.5 w-full rounded bg-surface-2"
              >
                <div className="h-full rounded bg-brand-cyan" style={{ width: `${confidence}%` }} />
              </div>
              <p className="mt-0.5 text-xs text-text-muted">confidence {confidence}%</p>
            </div>
          )}
          {entry.suggestions.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1">
              {entry.suggestions.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-text-muted">
                  <span aria-hidden>☐</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          )}
          {entry.diagnosisMeta && (
            <p className="mt-1.5 text-xs text-text-faint">{entry.diagnosisMeta}</p>
          )}
        </Section>

        {loading ? (
          <p className="mt-4 text-sm text-text-faint">Loading run report…</p>
        ) : error === "expired" ? (
          <p className="mt-4 rounded-md border border-warn/40 bg-warn/10 p-2.5 text-xs text-warn">
            Run expired — the run store is in memory and this run is gone. Live fields above are
            all that remains.
          </p>
        ) : error ? (
          <p className="mt-4 text-sm text-crit">{error}</p>
        ) : (
          <>
            {verification && (
              <Section title={entry.domain === "appliance" ? "Safety evidence" : "Tests"}>
                <VerifyBlock verification={verification} />
                {verifyMs > 0 && (
                  <p className="mt-1 text-xs tabular-nums text-text-faint">
                    verify took {Math.round(verifyMs)} ms
                  </p>
                )}
              </Section>
            )}

            {rows.length > 0 && (
              <Section title={`Code diff · ${changed} changed lines`}>
                <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border font-mono text-[11px] leading-5">
                  <p className="bg-surface-2 px-2 py-1 text-text-faint">original</p>
                  <p className="bg-surface-2 px-2 py-1 text-text-faint">patch</p>
                  <pre className="max-h-72 overflow-auto bg-surface p-2 whitespace-pre-wrap text-text-muted">
                    {rows.map((row, i) =>
                      row.kind === "add" ? (
                        <span key={i} className="block">
                          {"\n"}
                        </span>
                      ) : (
                        <span
                          key={i}
                          className={`block ${row.kind === "del" ? "bg-crit/15 text-crit" : ""}`}
                        >
                          {row.left || " "}
                        </span>
                      ),
                    )}
                  </pre>
                  <pre className="max-h-72 overflow-auto bg-surface p-2 whitespace-pre-wrap text-text-muted">
                    {rows.map((row, i) =>
                      row.kind === "del" ? (
                        <span key={i} className="block">
                          {"\n"}
                        </span>
                      ) : (
                        <span
                          key={i}
                          className={`block ${row.kind === "add" ? "bg-ok/15 text-ok" : ""}`}
                        >
                          {row.kind === "add" ? row.right : row.right || " "}
                        </span>
                      ),
                    )}
                  </pre>
                </div>
              </Section>
            )}

            {attempts.length > 0 && (
              <Section title="Attempts">
                <ol className="flex flex-col gap-1.5">
                  {attempts.map((step, i) => (
                    <li
                      key={i}
                      className="rounded-md border border-border bg-surface-2 p-2 text-xs"
                    >
                      <p className="text-text">
                        {str(step.step)} {typeof step.attempt === "number" ? `#${step.attempt}` : ""} ·{" "}
                        {str(step.status) || "—"}
                      </p>
                      <p className="mt-0.5 text-text-muted">
                        {modelProvider(str(step.model))}
                        {typeof step.duration_ms === "number" && step.duration_ms > 0
                          ? ` · ${Math.round(step.duration_ms)} ms`
                          : ""}
                      </p>
                      {str(step.message) && (
                        <p className="mt-0.5 text-text-faint">{str(step.message)}</p>
                      )}
                    </li>
                  ))}
                </ol>
              </Section>
            )}

            <Section title="Result">
              {prUrl ? (
                <a
                  href={prUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-block rounded-md border border-brand-cyan/50 px-3 py-1.5 text-sm text-brand-cyan hover:underline"
                >
                  View PR on GitHub ↗
                </a>
              ) : runbookSteps.length > 0 ? (
                <div className="rounded-md border border-border bg-surface-2 p-2.5 text-xs">
                  {(str(alert.work_order_id) || str(alert.work_order)) && (
                    <p className="font-medium text-text">
                      Work order {str(alert.work_order_id) || str(alert.work_order)}
                    </p>
                  )}
                  {str(alert.message) && (
                    <p className="mt-0.5 text-text-muted">{str(alert.message)}</p>
                  )}
                  <ol className="mt-1.5 flex flex-col gap-1">
                    {runbookSteps.map((step, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-text-muted">
                        <span aria-hidden>🛡</span>
                        <span>{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : (
                <p className="text-sm text-text-faint">
                  {entry.final || (status ? `status: ${status}` : "No result yet.")}
                </p>
              )}
              {status === "PASS" && (
                <div className="mt-2">
                  <button
                    type="button"
                    onClick={apply}
                    className="rounded-md bg-ok px-3 py-1.5 text-sm font-semibold text-[#0b1710] hover:brightness-110"
                  >
                    {entry.domain === "software" ? "Apply fix to shop" : "Apply runbook to fridge"}
                  </button>
                  {!operatorToken && (
                    <p className="mt-1 text-xs text-text-faint">
                      Needs the operator token — you’ll be asked for it.
                    </p>
                  )}
                </div>
              )}
            </Section>

            {decision && (
              <Section title="Decision record">
                <pre className="max-h-40 overflow-auto rounded-md border border-border bg-surface-2 p-2 font-mono text-[11px] whitespace-pre-wrap text-text-muted">
                  {JSON.stringify(decision, null, 2).slice(0, 3000)}
                </pre>
              </Section>
            )}

            {(str(gate.decision) || checks.length > 0) && (
              <Section title="Gate checks">
                {str(gate.decision) && (
                  <p className="text-xs text-text-muted">
                    {str(gate.decision)}
                    {str(gate.rule) ? ` · ${str(gate.rule)}` : ""}
                    {str(gate.reason) ? ` — ${str(gate.reason)}` : ""}
                  </p>
                )}
                {checks.length > 0 && (
                  <ul className="mt-1.5 flex flex-col gap-1">
                    {checks.map((check, i) => (
                      <li key={i} className="text-xs text-text-muted">
                        <span className="font-medium text-text">{check.name}</span> · {check.result}
                        {check.detail ? ` — ${check.detail}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
