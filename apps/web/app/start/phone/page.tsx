"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import Logo from "../../components/Logo";
import ThemeToggle from "../../components/ThemeToggle";
import { apiUrl, responseDetail } from "../../lib/api";
import { Card } from "../../ui";
import ApkQr from "../../welcome/ApkQr";

/** Last setup step: the phone app, downloaded and connected before the demo. */
export default function PhoneSetupPage() {
  const [pairApi, setPairApi] = useState<string | null>(null);
  const [pairFailed, setPairFailed] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/api/pairing`);
        if (!response.ok) throw new Error(await responseDetail(response));
        const body = (await response.json()) as { api_url?: unknown };
        if (typeof body.api_url !== "string") {
          throw new Error("Pairing URL unavailable.");
        }
        if (!cancelled) setPairApi(body.api_url);
      } catch (err) {
        if (!cancelled) {
          setPairFailed(
            err instanceof Error ? err.message : "Pairing failed.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function copyApiUrl() {
    if (!pairApi) return;
    try {
      await navigator.clipboard.writeText(pairApi);
      setCopied(true);
    } catch {
      setCopied(false);
      setPairFailed("Copy failed — long-press the URL to copy it by hand.");
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg font-sans text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-1.5 px-4 py-3">
          <Link
            href="/welcome"
            title="Home"
            aria-label="TelemetryAgent home"
            className="rounded outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <Logo size={16} />
          </Link>
          <span className="text-sm font-semibold">Guided setup</span>
          <span className="ms-auto text-xs text-text-muted">
            Last step · Phone
          </span>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-3 px-4 py-6">
        <Card title="Download the Android app">
          <p className="text-sm text-text-muted">
            One APK for the demo and for production. Install it now — the
            next card connects it before the demo opens.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-5">
            <a
              href="/downloads/telemetry-agent.apk"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
            >
              Download APK
            </a>
            <figure className="flex items-center gap-3">
              <span className="rounded-md bg-white p-2">
                <ApkQr />
              </span>
              <figcaption className="text-xs leading-relaxed text-text-muted">
                Point your phone camera
                <br />
                to download the APK
              </figcaption>
            </figure>
          </div>
        </Card>

        <Card title="Connect it to this demo">
          {!pairApi && !pairFailed && (
            <p className="text-sm text-text-muted" role="status">
              Fetching this demo&apos;s connection details…
            </p>
          )}
          {pairFailed && !pairApi && (
            <p className="text-sm text-crit" role="alert">
              {pairFailed} You can still continue — pair from Mission Control
              later.
            </p>
          )}
          {pairApi && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-4">
                <span className="rounded-md bg-white p-2">
                  <QRCodeSVG
                    value={JSON.stringify({ api: pairApi })}
                    size={120}
                    aria-label="QR code: connect the app to this demo"
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-text-faint">API URL</p>
                  <p className="mt-1 font-mono text-xs break-all text-text">
                    {pairApi}
                  </p>
                  <button
                    type="button"
                    onClick={() => void copyApiUrl()}
                    className="mt-2 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    {copied ? "Copied ✓" : "Copy"}
                  </button>
                </div>
              </div>
              <ol className="list-decimal space-y-1.5 ps-5 text-xs leading-relaxed text-text-muted">
                <li>Open the app and tap Connect.</li>
                <li>
                  Point the camera at the code — or type the API URL above.
                </li>
                <li>
                  Leave Mobile token blank on the public demo. On your own
                  API, type the mobile token from its .env.
                </li>
              </ol>
            </div>
          )}
        </Card>

        <div>
          <Link
            href="/?tour=1"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
          >
            Continue to the demo →
          </Link>
        </div>
      </main>
    </div>
  );
}
