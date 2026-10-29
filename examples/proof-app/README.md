# proof-shop — the app TelemetryAgent proves itself on

A tiny FastAPI cart service with one real bug: checking out an **empty
cart** crashes with `ZeroDivisionError` (`app/cart.py`, `summary()`).
The suite (20 tests) is green on the buggy code — the empty cart is the
case nobody tested, and the one TelemetryAgent writes, proves, and fixes.

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest -q                       # 20 passed
uvicorn app.main:app --port 8103 > app.log 2>&1 &
python trigger_bug.py           # POSTs {"items": []} -> 500 + traceback
tail -20 app.log                # the traceback the forwarder ships
```

## Ship logs to TelemetryAgent

```bash
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file app.log --service proof-shop
```

`/connect` prints this one-liner with the real key filled in.

## Deploy to Railway

Push this folder to its own repo (`maximuskay2/telemetryAgent-proof-app`),
then Railway → New → Deploy from Repo. The `Procfile` is the start
command (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`); no build
step needed. On Railway, stdout is the log drain: point the forwarder
(or the Sentry webhook) at it per `/connect` step 2.

## What the proof run does

1. `trigger_bug.py` → traceback → forwarder → TelemetryAgent.
2. Agent locates `app/cart.py`, reproduces in a sandbox, patches the
   empty-cart guard, proves the suite stays green, opens a PR here.
3. Merge → Railway redeploys → `trigger_bug.py` returns 200 with
   `average_item_price: 0.0`.
