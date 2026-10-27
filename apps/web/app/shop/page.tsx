"use client";

import { useEffect, useRef, useState } from "react";

type Product = { sku: string; name: string; price: number; stock: number };
type Toast = { id: number; text: string; ok: boolean };

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const shopUrl = process.env.NEXT_PUBLIC_SHOP_URL ?? "http://localhost:8002";
const SPARK_POINTS = 40;

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="hint">waiting for metrics…</span>;
  const max = Math.max(0.05, ...values);
  const step = 100 / (SPARK_POINTS - 1);
  const points = values
    .slice(-SPARK_POINTS)
    .map((v, i) => `${(i * step).toFixed(1)},${(28 - (v / max) * 26).toFixed(1)}`)
    .join(" ");
  return (
    <svg className="spark" viewBox="0 0 100 30" aria-label="Error rate">
      <polyline points={points} />
    </svg>
  );
}

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
          setErrorRate((current) => [...current, rate].slice(-SPARK_POINTS));
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
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AUTOPARTS LAGOS · LIVE SHOP</p>
          <h1>Shop</h1>
        </div>
        <div className={`status ${status === "open" ? "connected" : "disconnected"}`}>
          <span className="status-dot" />
          {status}
        </div>
      </header>

      <section className={`panel shop-banner ${failing ? "failing" : ""}`}>
        <div>
          <p className="eyebrow">ERROR RATE · LIVE</p>
          <p className="bignum">
            {errorRate.length > 0
              ? `${((errorRate[errorRate.length - 1] ?? 0) * 100).toFixed(1)}%`
              : "—"}
          </p>
        </div>
        <Sparkline values={errorRate} />
      </section>

      <section className="product-grid">
        {products.map((product) => (
          <article className="panel product" key={product.sku}>
            <p className="eyebrow">{product.sku}</p>
            <h2>{product.name}</h2>
            <p className="price">${product.price.toFixed(2)}</p>
            <p className="hint">stock: {product.stock}</p>
            <button
              type="button"
              disabled={buying !== null}
              onClick={() => buy(product.sku)}
            >
              {buying === product.sku ? "Placing…" : "Buy"}
            </button>
          </article>
        ))}
      </section>

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <p key={t.id} className={t.ok ? "toast ok" : "toast bad"}>
            {t.text}
          </p>
        ))}
      </div>

      <footer>
        <a href="/">← Telemetry Agent</a> · shop {shopUrl}
      </footer>
    </main>
  );
}
