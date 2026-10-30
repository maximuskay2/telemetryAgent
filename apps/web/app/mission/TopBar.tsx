"use client";

import { Bell, BellOff, KeyRound, Pause, Play, Presentation, QrCode, RotateCcw, Scan } from "lucide-react";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";
import { apiUrl, responseDetail } from "../lib/api";
import ThemeToggle from "../components/ThemeToggle";
import { StatusDot } from "../ui";
import { useMission } from "./state";

const MODELS = ["Muse Spark", "Spark Open", "Wonder", "Sandbox"];

function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function useDismiss(onDismiss: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    const onClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onDismiss();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [onDismiss]);
  return ref;
}

function PairButton() {
  const [open, setOpen] = useState(false);
  const [pairUrl, setPairUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState("");
  const ref = useDismiss(() => setOpen(false));

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setFailed("");
    if (pairUrl) return;
    try {
      const response = await fetch(`${apiUrl}/api/pairing`);
      if (!response.ok) throw new Error(await responseDetail(response));
      const body = (await response.json()) as { api_url?: unknown };
      if (typeof body.api_url !== "string") throw new Error("Pairing URL unavailable.");
      setPairUrl(body.api_url);
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "Pairing failed.");
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => void toggle()}
        title="Pair phone (F17)"
        aria-label="Pair phone"
        aria-expanded={open}
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface-2 p-2 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
      >
        <QrCode size={15} />
        <span className="hidden text-xs xl:inline">Pair</span>
      </button>
      {open && (
        <div className="absolute top-full right-0 z-50 mt-2 w-64 rounded-[10px] border border-border bg-surface-2 p-3 shadow-2xl">
          <p className="mb-2 text-xs font-medium text-text">Pair phone</p>
          {pairUrl ? (
            <>
              <QRCodeSVG value={JSON.stringify({ api: pairUrl })} size={120} />
              <p className="mt-2 font-mono text-[11px] break-all text-text-muted">{pairUrl}</p>
              <p className="mt-1 text-[11px] text-text-faint">
                Same Wi-Fi, then type the mobile token from .env into the app.
              </p>
            </>
          ) : (
            <p className="text-xs text-text-muted">{failed || "Loading…"}</p>
          )}
        </div>
      )}
    </div>
  );
}

function TokenButton() {
  const { operatorToken, setOperatorToken, tokenOpen, setTokenOpen } = useMission();
  const [draft, setDraft] = useState(operatorToken);
  const ref = useDismiss(() => setTokenOpen(false));

  useEffect(() => {
    if (tokenOpen) setDraft(operatorToken);
  }, [tokenOpen, operatorToken]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setTokenOpen(!tokenOpen)}
        title="Operator token (needed for apply/approve when MOBILE_API_TOKEN is set)"
        aria-label="Operator token"
        aria-expanded={tokenOpen}
        className="relative inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface-2 p-2 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
      >
        <KeyRound size={15} />
        <span className="hidden text-xs xl:inline">Token</span>
        {operatorToken && (
          <span className="absolute top-1 right-1 size-1.5 rounded-full bg-ok" aria-hidden />
        )}
      </button>
      {tokenOpen && (
        <div className="absolute top-full right-0 z-50 mt-2 w-72 rounded-[10px] border border-border bg-surface-2 p-3 shadow-2xl">
          <p className="mb-1 text-xs font-medium text-text">Operator token</p>
          <p className="mb-2 text-[11px] text-text-faint">
            Same value as the server&apos;s MOBILE_API_TOKEN. Kept in this tab only, sent as
            X-Mobile-Token.
          </p>
          <input
            type="password"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setOperatorToken(draft.trim());
                setTokenOpen(false);
              }
            }}
            placeholder="Paste token…"
            autoComplete="off"
            className="w-full rounded-lg border border-border bg-bg px-2 py-1.5 font-mono text-xs text-text outline-none placeholder:text-text-faint focus:border-brand"
          />
          <div className="mt-2 flex justify-end gap-2">
            {operatorToken && (
              <button
                type="button"
                onClick={() => {
                  setOperatorToken("");
                  setTokenOpen(false);
                }}
                className="cursor-pointer rounded-lg px-2 py-1 text-xs text-text-muted hover:text-text"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setOperatorToken(draft.trim());
                setTokenOpen(false);
              }}
              className="cursor-pointer rounded-lg bg-brand px-3 py-1 text-xs font-medium text-on-brand hover:bg-brand/90"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TopBar() {
  const {
    systems,
    baselinePct,
    warnFixMs,
    counts,
    runningModels,
    connection,
    scenario,
    playScenario,
    resetWorld,
    soundOn,
    setSoundOn,
    focusMode,
    setFocusMode,
    presenterMode,
    setPresenterMode,
  } = useMission();
  const live = connection === "connected";
  const anyArmed = systems.some((system) => system.status === "armed");

  return (
    <header className="border-b border-border bg-surface">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
        <Link
          href="/welcome"
          title="Home"
          aria-label="TelemetryAgent home"
          className="flex items-center gap-1.5 outline-none focus-visible:ring-2 focus-visible:ring-brand rounded"
        >
          <span className="text-sm text-brand-cyan" aria-hidden>
            ◆
          </span>
          <span className="text-sm font-semibold text-text">TelemetryAgent</span>
        </Link>
        <nav aria-label="Systems" className="flex flex-wrap items-center gap-1.5">
          {systems.map((system) => {
            const pct = baselinePct[system.system_id];
            if (system.status === "armed") {
              return (
                <Link
                  key={system.system_id}
                  href={`/setup?system=${system.system_id}`}
                  className="inline-flex items-center gap-1 rounded-full border border-ok/40 bg-ok/10 px-2 py-0.5 text-xs font-medium text-ok"
                >
                  <span className="size-1.5 rounded-full bg-ok" aria-hidden />
                  {system.name} · Watching
                </Link>
              );
            }
            if (system.status === "learning") {
              return (
                <Link
                  key={system.system_id}
                  href={`/setup?system=${system.system_id}`}
                  className="inline-flex items-center gap-1 rounded-full border border-brand/40 bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand-cyan"
                >
                  <span className="size-1.5 rounded-full bg-brand" aria-hidden />
                  {system.name} · Watching normal{pct !== undefined ? ` ${pct}%` : ""}
                </Link>
              );
            }
            return (
              <Link
                key={system.system_id}
                href={`/setup?system=${system.system_id}`}
                className="inline-flex items-center gap-1 rounded-full border border-warn/40 bg-warn/10 px-2 py-0.5 text-xs font-medium text-warn"
              >
                <span className="size-1.5 rounded-full bg-warn" aria-hidden />
                {system.name} · Not watching yet — set up
              </Link>
            );
          })}
        </nav>
        <div className="ms-auto flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-xs tabular-nums text-text-muted" title="First watcher warning to applied fix (or verified PASS)">
            Warning → fix:{" "}
            <strong className="text-text">{warnFixMs === null ? "—" : formatDuration(warnFixMs)}</strong>
          </span>
          <span className="text-xs text-text-muted" title="Gate decisions this session">
            Ignored as normal <strong className="text-ok tabular-nums">{counts.suppress}</strong>
            {" · "}Acting <strong className="text-crit tabular-nums">{counts.act}</strong>
          </span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border px-3 py-1.5">
        <div className="flex items-center gap-1.5" aria-label="Models running">
          {MODELS.map((model) => {
            const lit = runningModels.includes(model);
            return (
              <span
                key={model}
                className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                  lit
                    ? "border-brand/50 bg-brand/15 text-brand-cyan"
                    : "border-border text-text-faint"
                }`}
              >
                {model}
              </span>
            );
          })}
        </div>
        <div className="ms-auto flex items-center gap-1.5">
          <Link
            href="/welcome"
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            ← Home
          </Link>
          <Link
            href="/start"
            className="rounded-lg border border-brand/50 bg-brand/10 px-2.5 py-1.5 text-xs font-medium text-brand-cyan outline-none hover:bg-brand/20 focus-visible:ring-2 focus-visible:ring-brand"
          >
            Guided demo
          </Link>
          <Link
            href="/shop"
            className="rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            Storefront ↗
          </Link>
          <StatusDot tone={live ? "ok" : "warn"} pulse={!live} label={live ? "Live" : "Reconnecting"} />
          <button
            type="button"
            onClick={() => void playScenario()}
            disabled={scenario.playing || !anyArmed}
            title={
              !anyArmed
                ? "Finish setup first"
                : "Play full demo, 2 min (F2)"
            }
            aria-label={
              scenario.playing
                ? "Full demo playing"
                : !anyArmed
                  ? "Play full demo (finish setup first)"
                  : "Play full demo"
            }
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface-2 p-2 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
          >
            {scenario.playing ? <Pause size={15} /> : <Play size={15} />}
            <span className="hidden text-xs whitespace-nowrap xl:inline">Play full demo</span>
          </button>
          <button
            type="button"
            onClick={() => void resetWorld()}
            title="Restart demo (F2)"
            aria-label="Restart demo"
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface-2 p-2 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            <RotateCcw size={15} />
            <span className="hidden text-xs whitespace-nowrap xl:inline">Restart demo</span>
          </button>
          <PairButton />
          <TokenButton />
          <button
            type="button"
            onClick={() => setSoundOn(!soundOn)}
            title={soundOn ? "Veto sound on" : "Veto sound off"}
            aria-label={soundOn ? "Mute veto sound" : "Unmute veto sound"}
            aria-pressed={soundOn}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface-2 p-2 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            {soundOn ? <Bell size={15} /> : <BellOff size={15} />}
            <span className="hidden text-xs xl:inline">Sound</span>
          </button>
          <button
            type="button"
            onClick={() => setFocusMode(!focusMode)}
            title="Focus mode — incidents only (F)"
            aria-label={focusMode ? "Exit focus mode" : "Enter focus mode"}
            aria-pressed={focusMode}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface-2 p-2 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            <Scan size={15} />
            <span className="hidden text-xs xl:inline">Focus</span>
          </button>
          <button
            type="button"
            onClick={() => setPresenterMode(!presenterMode)}
            title="Presenter mode — larger (P)"
            aria-label={presenterMode ? "Exit presenter mode" : "Enter presenter mode"}
            aria-pressed={presenterMode}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface-2 p-2 text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            <Presentation size={15} />
            <span className="hidden text-xs xl:inline">Present</span>
          </button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
