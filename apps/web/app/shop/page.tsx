"use client";

import { useEffect, useRef, useState } from "react";
import ThemeToggle from "../components/ThemeToggle";
import { apiUrl } from "../lib/api";
import { Sparkline } from "../ui";

type Product = { sku: string; name: string; price: number; stock: number };
type Toast = { id: number; text: string; ok: boolean };

function resolveShopUrl(): string {
  const explicit = (process.env.NEXT_PUBLIC_SHOP_URL ?? "").replace(/\/$/, "");
  const leftoverLocal =
    !explicit ||
    explicit.includes("localhost") ||
    explicit.includes("127.0.0.1");
  if (leftoverLocal && !apiUrl.includes("localhost")) {
    return `${apiUrl.replace(/\/$/, "")}/shop-api`;
  }
  if (explicit) return explicit;
  return "http://localhost:8002";
}

const shopUrl = resolveShopUrl();

export default function ShopPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [buying, setBuying] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [errorRate, setErrorRate] = useState<number[]>([]);
  const [status, setStatus] = useState("loading");
  const toastId = useRef(0);

  function toast(text: string, ok: boolean) {
    const id = ++toastId.current;
    setToasts((current) => [...current.slice(-4), { id, text, ok }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
    }, 4000);
  }

  async function refreshProducts() {
    try {
      const response = await fetch(`${shopUrl}/products`);
      if (!response.ok) throw new Error(`shop returned ${response.status}`);
      const body = (await response.json()) as { products?: Product[] };
      setProducts(body.products ?? []);
      setStatus("open");
    } catch {
      setStatus("unreachable");
    }
  }

  useEffect(() => {
    refreshProducts();
    const socket = new WebSocket(`${apiUrl.replace(/^http/, "ws")}/api/ws`);
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as {
          kind?: string;
          payload?: { error_rate?: unknown };
        };
        const rate = data.payload?.error_rate;
        if (data.kind === "shop_metrics" && typeof rate === "number") {
          setErrorRate((current) => [...current, rate].slice(-60));
        }
      } catch {
        // ignore malformed frames
      }
    };
    const timer = window.setInterval(refreshProducts, 5000);
    return () => {
      socket.close();
      window.clearInterval(timer);
    };
  }, []);

  async function buy(sku: string) {
    const others = products.map((p) => p.sku).filter((s) => s !== sku);
    const companion = others[Math.floor(Math.random() * others.length)];
    setBuying(sku);
    try {
      const response = await fetch(`${shopUrl}/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: [sku, companion] }),
      });
      const body = (await response.json()) as { order_id?: string };
      if (!response.ok) throw new Error(`order ${body.order_id ?? ""} failed`.trim());
      toast(`Order ${body.order_id} placed`, true);
    } catch {
      toast("Order failed — the shop is struggling", false);
    } finally {
      setBuying(null);
      refreshProducts();
    }
  }

  const failing =
    errorRate.length > 0 && errorRate[errorRate.length - 1] > 0.05;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-4 bg-bg p-4 text-text">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-ok/20 pb-3">
        <div>
          <p className="text-[11px] font-semibold tracking-wide text-ok/80 uppercase">
            AutoParts Lagos · Customer storefront
          </p>
          <h1 className="text-2xl font-bold text-text">Shop</h1>
        </div>
        <nav aria-label="Demo navigation" className="flex items-center gap-2">
          <a
            href="/welcome"
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            ← Home
          </a>
          <a
            href="/"
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-[13px] font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
          >
            ← Mission Control
          </a>
          <a
            href="/start"
            className="rounded-lg border border-brand/50 bg-brand/10 px-3 py-1.5 text-[13px] font-medium text-brand-cyan outline-none hover:bg-brand/20 focus-visible:ring-2 focus-visible:ring-brand"
          >
            Guided demo
          </a>
          <ThemeToggle />
        </nav>
        <p
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
            status === "open"
              ? "border-ok/40 bg-ok/10 text-ok"
              : "border-crit/40 bg-crit/10 text-crit"
          }`}
        >
          <span
            className={`size-1.5 rounded-full ${status === "open" ? "bg-ok" : "bg-crit"}`}
          />
          {status}
        </p>
      </header>

      <section
        aria-label="Live error rate"
        className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 ${
          failing ? "border-crit/50 bg-crit/10" : "border-border bg-surface"
        }`}
      >
        <div>
          <p className="text-[11px] font-semibold tracking-wide text-text-faint uppercase">
            Error rate · live
          </p>
          <p className="text-3xl tabular-nums text-text">
            {errorRate.length > 0
              ? `${((errorRate[errorRate.length - 1] ?? 0) * 100).toFixed(1)}%`
              : "—"}
          </p>
        </div>
        <span className={failing ? "text-crit" : "text-ok/70"}>
          <Sparkline points={errorRate.length > 1 ? errorRate : [0, 0]} width={220} height={40} />
        </span>
      </section>

      <section
        aria-label="Products"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        {products.map((product) => (
          <article
            key={product.sku}
            className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4"
          >
            <p className="font-mono text-[11px] text-text-faint">{product.sku}</p>
            <h2 className="text-base font-semibold">{product.name}</h2>
            <p className="text-xl tabular-nums text-text">${product.price.toFixed(2)}</p>
            <p className="text-xs text-text-muted">stock: {product.stock}</p>
            <button
              type="button"
              disabled={buying !== null}
              onClick={() => buy(product.sku)}
              className="mt-2 cursor-pointer rounded-lg bg-brand px-3 py-2 text-sm font-semibold text-on-brand hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {buying === product.sku ? "Placing…" : "Buy"}
            </button>
          </article>
        ))}
      </section>

      <div className="flex flex-col gap-1" aria-live="polite">
        {toasts.map((t) => (
          <p
            key={t.id}
            className={`rounded-lg border p-2 text-sm ${
              t.ok
                ? "border-ok/40 bg-ok/10 text-ok"
                : "border-crit/40 bg-crit/10 text-crit"
            }`}
          >
            {t.text}
          </p>
        ))}
      </div>

      <footer className="mt-auto text-xs text-text-faint">
        <a href="/" className="hover:underline">
          ← Telemetry Agent
        </a>{" "}
        · shop {shopUrl}
      </footer>
    </main>
  );
}
