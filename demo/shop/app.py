"""AutoParts Lagos mini shop (Sim 1): a real app that really fails.

`GET /products`, `POST /orders` (moves stock between 2-3 SKUs). Orders lock
inventory rows through an **active module path** (`INVENTORY_PATH`, default
the buggy `demo/target-service/inventory.py`), so Sim 5 can hot-swap a patched
copy without touching the original. Timeouts live here, not in inventory.py:
a stuck acquire becomes WARN retries, then an ERROR deadlock block.
"""

from __future__ import annotations

import importlib.util
import os
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INVENTORY = os.path.normpath(
    os.path.join(HERE, "..", "target-service", "inventory.py")
)
LOG_PATH = os.path.join(HERE, "logs", "shop.log")
ACQUIRE_TIMEOUT_S = 0.1
HOLD_S = 0.008
MAX_ATTEMPTS = 3

CATALOG = [
    {"sku": "axle", "name": "Axle assembly", "price": 129.99},
    {"sku": "brake-pad", "name": "Brake pad set", "price": 49.99},
    {"sku": "chain", "name": "Drive chain", "price": 24.99},
    {"sku": "sprocket", "name": "Sprocket", "price": 19.99},
    {"sku": "gasket", "name": "Gasket kit", "price": 9.99},
    {"sku": "piston", "name": "Piston", "price": 59.99},
    {"sku": "alternator", "name": "Alternator", "price": 189.99},
    {"sku": "starter", "name": "Starter motor", "price": 149.99},
    {"sku": "radiator", "name": "Radiator", "price": 119.99},
    {"sku": "muffler", "name": "Muffler", "price": 89.99},
    {"sku": "shock", "name": "Shock absorber", "price": 69.99},
    {"sku": "headlight", "name": "Headlight", "price": 39.99},
]


def load_inventory(path: str):
    """Import the inventory module from an explicit file path."""
    spec = importlib.util.spec_from_file_location("shop_inventory", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class ShopLogger:
    def __init__(self, path: str = LOG_PATH) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.handle = open(path, "a", encoding="utf-8")
        self.lock = threading.Lock()

    def log(self, line: str) -> None:
        with self.lock:
            self.handle.write(f"{_stamp()} {line}\n")
            self.handle.flush()

    def close(self) -> None:
        with self.lock:
            self.handle.close()


class Metrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.orders: deque = deque(maxlen=2000)  # (ts, ok, latency_ms)

    def record(self, ok: bool, latency_ms: float) -> None:
        with self.lock:
            self.orders.append((time.time(), ok, latency_ms))

    def snapshot(self, window_s: float = 60.0) -> dict:
        now = time.time()
        with self.lock:
            recent = [o for o in self.orders if now - o[0] <= window_s]
        if not recent:
            return {"orders_per_min": 0.0, "error_rate": 0.0, "p95_ms": 0.0}
        latencies = sorted(o[2] for o in recent)
        errors = sum(1 for o in recent if not o[1])
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        span = max(1.0, now - recent[0][0])
        return {
            "orders_per_min": round(len(recent) * 60.0 / span, 1),
            "error_rate": round(errors / len(recent), 3),
            "p95_ms": round(p95, 1),
        }


def publish_event(api_base: str, kind: str, payload: dict) -> None:
    """Best-effort SimEvent publish; the shop never blocks on the agent API."""
    try:
        httpx.post(
            f"{api_base.rstrip('/')}/api/sim/events",
            json={"kind": kind, "payload": payload},
            timeout=2.0,
        )
    except httpx.HTTPError:
        pass


class Shop:
    def __init__(
        self,
        inventory_path: str = DEFAULT_INVENTORY,
        log_path: str = LOG_PATH,
        api_base: str = "http://localhost:8001",
    ) -> None:
        self.inventory = load_inventory(inventory_path)
        self.inventory_path = inventory_path
        self.log = ShopLogger(log_path)
        self.metrics = Metrics()
        self.api_base = api_base
        self.stock = {item["sku"]: 100 for item in CATALOG}
        self.stock_lock = threading.Lock()

    def acquire_timed(self, items: list, timeout_s: float = ACQUIRE_TIMEOUT_S):
        """Acquire via the active inventory module with a timeout."""
        box: dict = {}
        thread = threading.Thread(
            target=lambda: box.setdefault(
                "held", self.inventory.acquire_all(items)
            ),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            return None, True
        return box["held"], False

    def place_order(self, items: list[str]) -> dict:
        """Fulfil an order; returns ok/failed with latency. Never raises."""
        order_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()
        skus = [sku for sku in items if sku in self.stock]
        if len(skus) < 2:
            return {"order_id": order_id, "status": "failed",
                    "reason": "need 2-3 known SKUs", "latency_ms": 0.0}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            held, timed_out = self.acquire_timed(skus)
            if timed_out:
                backoff_ms = min(100, 10 * (2 ** attempt))
                self.log.log(
                    f"WARNING retry={attempt} order={order_id} "
                    f"backoff_ms={backoff_ms} items={','.join(skus)} "
                    "(lock wait timeout)"
                )
                time.sleep(backoff_ms / 1000.0)
                continue
            try:
                time.sleep(HOLD_S)  # row writes take ms: contention is real
                with self.stock_lock:
                    for sku in skus[1:]:
                        self.stock[sku] -= 1
                    self.stock[skus[0]] += len(skus) - 1
            finally:
                self.inventory.release_all(held)
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.record(True, latency_ms)
            self._emit_order(order_id, True, latency_ms, skus)
            return {"order_id": order_id, "status": "ok",
                    "latency_ms": round(latency_ms, 1)}
        latency_ms = (time.perf_counter() - started) * 1000.0
        self.log.log(f"ERROR order={order_id} service=shop items={','.join(skus)}")
        self.log.log(
            "Deadlock detected while acquiring lock on inventory_items; "
            "transaction rolled back."
        )
        self.metrics.record(False, latency_ms)
        self._emit_order(order_id, False, latency_ms, skus)
        return {"order_id": order_id, "status": "failed",
                "reason": "deadlock", "latency_ms": round(latency_ms, 1)}

    def _emit_order(self, order_id: str, ok: bool, latency_ms: float, skus: list) -> None:
        publish_event(
            self.api_base,
            "shop_order",
            {"order_id": order_id,
             "status": "ok" if ok else "failed",
             "latency_ms": round(latency_ms, 1),
             "items": skus},
        )

    def products(self) -> list:
        with self.stock_lock:
            return [{**item, "stock": self.stock[item["sku"]]} for item in CATALOG]


class OrderIn(BaseModel):
    items: list[str] = Field(min_length=2, max_length=3)


shop = Shop(
    inventory_path=os.environ.get("INVENTORY_PATH", DEFAULT_INVENTORY),
    api_base=os.environ.get("AGENT_API", "http://localhost:8001"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = threading.Event()
    threading.Thread(target=_metrics_loop, args=(stop,), daemon=True).start()
    yield
    stop.set()
    shop.log.close()


app = FastAPI(title="AutoParts Lagos (demo shop)", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "inventory": shop.inventory_path}


@app.get("/products")
def products() -> dict:
    return {"products": shop.products()}


@app.post("/orders", status_code=200)
def orders(payload: OrderIn) -> dict:
    result = shop.place_order(payload.items)
    if result["status"] == "failed":
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=result)
    return result


def _metrics_loop(stop: threading.Event) -> None:
    while not stop.wait(1.0):
        publish_event(shop.api_base, "shop_metrics", shop.metrics.snapshot())


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("SHOP_PORT", "8002"))
    uvicorn.run(app, host="127.0.0.1", port=port)
