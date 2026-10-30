# proof-shop-go — the Go app TelemetryAgent proves itself on

A tiny zero-dependency Go cart service (`net/http`, stdlib only) with
one real bug: checking out an **empty cart** panics with integer divide
by zero (`shop/cart.go`, `Summarize()` divides by `len(items)`). The
suite (21 tests) is green on the buggy code — the empty cart is the
case nobody tested, and the one TelemetryAgent writes, proves, and
fixes.

Wire shape matches `examples/proof-app` (Python): `POST /checkout` with
`{"items": [{"name", "price", "qty", "currency"?}]}` → `{"lines",
"subtotal", "discount", "total", "average_item_price", "currency"}`.
Money is integer cents inside, dollars on the wire.

The panic barrier logs the genuine goroutine stack (`panic: ...` +
`debug.Stack()`, byte-identical to an unrecovered `net/http` panic)
and answers 500 so one bad checkout cannot kill the server.

## Run locally

```bash
go test ./...                   # 21 passed
./trigger.sh                    # builds, starts its own server,
                                # POSTs {"items": []} -> 500 + the real
                                # goroutine stack, printed
```

## Suite in the sandbox image

```bash
docker run --rm -v "$PWD:/app" -w /app golang:1.23 go test ./...
```

Servers bind `127.0.0.1` by default; set `HOST=0.0.0.0` to run in a container or on Railway.

## Ship logs to TelemetryAgent

Run the server with stderr to a file and point the forwarder at it, same
as the Python app (`/connect` prints the one-liner):

```bash
go build -o /tmp/proofshop ./cmd/proofshop
/tmp/proofshop 8324 > app.log 2>&1 &
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file app.log --service proof-shop-go
```

## What the proof run does

1. `trigger.sh` → Go panic trace → forwarder → TelemetryAgent.
2. Agent locates `shop/cart.go`, reproduces in the Go sandbox, patches
   the empty-cart guard, proves the suite stays green, opens a PR here.
3. Merge → redeploy → `trigger.sh` returns 200 with
   `average_item_price: 0.0`.
