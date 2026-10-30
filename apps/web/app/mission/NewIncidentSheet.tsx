"use client";

import { useEffect, useState, type ChangeEvent } from "react";
import { apiUrl, responseDetail } from "../lib/api";
import { useMission } from "./state";

const MAX_LOG_CHARS = 200_000;
const TRIMMED_LINES = 1500;
const APPLIANCE_TYPES = ["fridge", "freezer"];
const APPLIANCE_FAULTS = [
  "door_open",
  "condenser_fouling",
  "power_surge",
  "rapid_restart",
  "defrost_stuck",
];

export default function NewIncidentSheet({ onClose }: { onClose: () => void }) {
  const { injectSoftware, injectAppliance } = useMission();
  const [logText, setLogText] = useState("");
  const [target, setTarget] = useState("inventory.py");
  const [trimNotice, setTrimNotice] = useState("");
  const [sheetError, setSheetError] = useState("");
  const [applianceType, setApplianceType] = useState(APPLIANCE_TYPES[0]);
  const [fault, setFault] = useState(APPLIANCE_FAULTS[0]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function loadSample() {
    setSheetError("");
    try {
      const response = await fetch(`${apiUrl}/api/samples/deadlock`);
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as { log_text?: unknown };
      if (typeof body.log_text !== "string" || !body.log_text) {
        throw new Error("Sample came back empty.");
      }
      setLogText(body.log_text);
      setTrimNotice("");
    } catch (err) {
      setSheetError(err instanceof Error ? err.message : "Could not load sample.");
    }
  }

  function readLogFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setSheetError("");
    const reader = new FileReader();
    reader.onload = () => {
      const raw = typeof reader.result === "string" ? reader.result : "";
      if (raw.length <= MAX_LOG_CHARS) {
        setLogText(raw);
        setTrimNotice("");
        return;
      }
      const kept = raw.split("\n").slice(-TRIMMED_LINES).join("\n");
      setLogText(kept.length <= MAX_LOG_CHARS ? kept : kept.slice(-MAX_LOG_CHARS));
      setTrimNotice(
        `File exceeded ${MAX_LOG_CHARS / 1000} KB; kept the last ${TRIMMED_LINES} lines.`,
      );
    };
    reader.onerror = () => setSheetError("Could not read that file.");
    reader.readAsText(file);
  }

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="New incident">
      <button
        type="button"
        aria-label="Close new incident"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-black/60"
      />
      <div className="absolute right-0 bottom-0 left-0 mx-auto max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-t-xl border border-border bg-bg p-4">
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-base font-semibold text-text">New incident</h2>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md border border-border bg-surface-2 px-2.5 py-1 text-xs text-text hover:border-text-faint"
          >
            Close ✕
          </button>
        </div>
        {sheetError && <p className="mt-2 text-xs text-crit">{sheetError}</p>}

        <h3 className="mt-4 text-xs font-semibold tracking-wide text-text-faint uppercase">
          Software · paste or upload a crash log
        </h3>
        <textarea
          aria-label="Crash log"
          value={logText}
          onChange={(event) => setLogText(event.target.value)}
          rows={6}
          placeholder="Paste a crash log, load the sample, or upload a file…"
          className="mt-1.5 w-full rounded-md border border-border bg-surface-2 p-2 font-mono text-xs text-text placeholder:text-text-faint"
        />
        {trimNotice && <p className="mt-1 text-xs text-warn">{trimNotice}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={loadSample}
            className="rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint"
          >
            Load sample
          </button>
          <label className="cursor-pointer rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-text hover:border-text-faint">
            Upload log
            <input type="file" accept=".log,.txt" onChange={readLogFile} className="hidden" />
          </label>
          <label htmlFor="mission-target" className="ml-1 text-xs text-text-muted">
            Target
          </label>
          <input
            id="mission-target"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            className="w-32 rounded-md border border-border bg-surface-2 px-2 py-1.5 font-mono text-xs text-text"
          />
          <button
            type="button"
            onClick={() => {
              injectSoftware(logText, target);
              onClose();
            }}
            className="ml-auto rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-on-brand hover:brightness-110"
          >
            Run →
          </button>
        </div>

        <h3 className="mt-5 text-xs font-semibold tracking-wide text-text-faint uppercase">
          Appliance · inject a fridge incident
        </h3>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <label htmlFor="mission-appliance" className="text-xs text-text-muted">
            Type
          </label>
          <select
            id="mission-appliance"
            value={applianceType}
            onChange={(event) => setApplianceType(event.target.value)}
            className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-xs text-text"
          >
            {APPLIANCE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <label htmlFor="mission-fault" className="text-xs text-text-muted">
            Fault
          </label>
          <select
            id="mission-fault"
            value={fault}
            onChange={(event) => setFault(event.target.value)}
            className="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-xs text-text"
          >
            {APPLIANCE_FAULTS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              injectAppliance(applianceType, fault);
              onClose();
            }}
            className="ml-auto rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-on-brand hover:brightness-110"
          >
            Inject →
          </button>
        </div>
      </div>
    </div>
  );
}
