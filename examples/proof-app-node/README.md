# proof-shop-node — the JS app TelemetryAgent proves itself on

A tiny zero-dependency Node cart service (`node:http` + `node:test`) with
one real bug: checking out an **empty cart** crashes with `TypeError`
(`src/cart.js`, `summary()` reads `items[0].currency`). The suite (21
tests) is green on the buggy code — the empty cart is the case nobody
tested, and the one TelemetryAgent writes, proves, and fixes.

Wire shape matches `examples/proof-app` (Python): `POST /checkout` with
`{"items": [{"name", "price", "qty", "currency"?}]}` → `{"lines",
"subtotal", "discount", "total", "average_item_price", "currency"}`.

## Run locally

```bash
npm test                        # 21 passed
./trigger.sh                    # starts its own server, POSTs {"items": []}
                                # -> 500 + the real V8 stack, printed
```

## Suite in the sandbox image

```bash
docker run --rm -v "$PWD:/app" -w /app node:20 npm test
```

Servers bind `127.0.0.1` by default; set `HOST=0.0.0.0` to run in a container or on Railway.

## Ship logs to TelemetryAgent

Run the server with stderr to a file and point the forwarder at it, same
as the Python app (`/connect` prints the one-liner):

```bash
node src/server.js 8321 > app.log 2>&1 &
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file app.log --service proof-shop-node
```

## What the proof run does

1. `trigger.sh` → V8 `TypeError` trace → forwarder → TelemetryAgent.
2. Agent locates `src/cart.js`, reproduces in the node sandbox, patches
   the empty-cart guard, proves the suite stays green, opens a PR here.
3. Merge → redeploy → `trigger.sh` returns 200 with
   `average_item_price: 0.0`.
