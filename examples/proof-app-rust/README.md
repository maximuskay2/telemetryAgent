# proof-shop-rust — the Rust app TelemetryAgent proves itself on

A tiny zero-dependency Rust cart service (std `TcpListener`, `cargo
test`) with one real bug: checking out an **empty cart** panics with
`attempt to divide by zero` (`src/cart.rs`, `summary()` divides by
`items.len()`). The suite (21 tests) is green on the buggy code — the
empty cart is the case nobody tested, and the one TelemetryAgent writes,
proves, and fixes.

Wire shape matches `examples/proof-app` (Python): `POST /checkout` with
`{"items": [{"name", "price", "qty", "currency"?}]}` → `{"lines",
"subtotal", "discount", "total", "average_item_price", "currency"}`.
Money is integer cents inside, dollars on the wire.

Run the server with `RUST_BACKTRACE=1` (as `trigger.sh` does) so a panic
prints the full backtrace frames, not just the panic line.

## Run locally

```bash
cargo test -q                     # 21 passed
./trigger.sh                      # builds, starts its own server,
                                  # POSTs {"items": []} -> 500 + the real
                                  # Rust panic + backtrace, printed
```

## Suite in the sandbox image

```bash
docker run --rm -v "$PWD:/app" -w /app rust:1-slim cargo test --offline
```

(`cargo fetch` first with network when the registry cache is empty;
this crate has no dependencies.)

Servers bind `127.0.0.1` by default; set `HOST=0.0.0.0` to run in a container or on Railway.

## Ship logs to TelemetryAgent

Run the server with stderr to a file and point the forwarder at it, same
as the Python app (`/connect` prints the one-liner):

```bash
cargo build -q
RUST_BACKTRACE=1 ./target/debug/proof-shop-rust 8325 > app.log 2>&1 &
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file app.log --service proof-shop-rust
```

## What the proof run does

1. `trigger.sh` → Rust panic trace → forwarder → TelemetryAgent.
2. Agent locates `src/cart.rs`, reproduces in the Rust sandbox, patches
   the empty-cart guard, proves the suite stays green, opens a PR here.
3. Merge → redeploy → `trigger.sh` returns 200 with
   `average_item_price: 0.0`.
