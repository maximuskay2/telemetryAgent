# 🎬 TelemetryAgent: Visual Simulation Roadmap

Companion to [`roadmap.md`](roadmap.md). Goal: judges **see** both systems break, see the agent catch the problem on its own, and see the system recover after the verified fix.

```
CRASH            →  GRAB              →  SUGGEST          →  VERIFY              →  FIX
real shop fails     log watcher          Muse Spark          Modal fail→pass        PR + shop recovers
virtual fridge      sensor watcher       diagnosis           safety rules           work order + fridge recovers
```

Chosen scope:

| Domain | Build | Bonus |
| :--- | :--- | :--- |
| Software | **S2** real mini shop that breaks + **S1** animated service map | — |
| Hardware | **H1** animated virtual fridge with live gauges | **H2** Wokwi virtual ESP32 running real firmware (15 s clip) |

Real ESP32 hardware in a fridge stays in "Next version".

---

## 🔌 What already exists (do not rebuild)

| Existing piece | File | How the simulation uses it |
| :--- | :--- | :--- |
| Buggy service (lock-ordering deadlock) | `demo/target-service/inventory.py` | The shop imports it; stays buggy (pinned by `tests/test_demo_fixture.py`) |
| Software loop | `core/agent/loop.py` → `run_diagnostic_loop(log_text, max_attempts, on_event, original_code, open_pr, run_id)` | Watcher-triggered runs call it with `original_code` = `inventory.py` for fail-to-pass |
| Appliance loop | `core/agent/loop.py` → `run_appliance_loop(telemetry, max_attempts, on_event, send_alert, run_id)` | Called with **real streamed readings** instead of `generate_window` |
| Sandbox verify | `core/verify/sandbox.py` → `verify_fix` / `verify_patch` | Unchanged |
| Safety validator | `core/verify/safety_rules.py` → `validate_runbook` | Unchanged; result shown in the fridge lane |
| PR opener | `core/actions/github_pr.py` → `open_fix_pr(..., code_path, test_path)` | Called with `code_path="inventory.py"` so the PR changes the real file |
| Alert + work order | `core/actions/notify.py` → `send_alert` | Unchanged |
| Fault signatures | `core/simulate/appliance.py` (`BASE_TEMP_C`, `BASE_CURRENT_A`, fault names) | Reused by the streaming fridge so both stay consistent |
| Event stream | `apps/api/main.py` → `EventHub`, `AgentStep`, `WS /api/ws` | New sim events go over the same socket |
| Dashboard | `apps/web/app/page.tsx` (`applyStep`, `Stage`) | Extended with lanes, map, fridge; existing panels keep working |

Rule: every phase keeps the existing 79 unit tests green (`venv/bin/python -m unittest discover -s tests`).

---

## 🗓️ Schedule

```
[Oct 28]          ──> Sim 0: Plumbing (API + event types)          + Sim 1 start
[Oct 28 - Oct 29] ──> Sim 1: Real mini shop + load generator
[Oct 29]          ──> Sim 2: Log watcher (autonomous grab)
[Oct 30]          ──> Sim 3: Service map + pipeline lanes in dashboard
[Oct 30 - Oct 31] ──> Sim 4: Virtual fridge + sensor watcher + animated fridge
[Oct 31]          ──> Sim 5: "Proof it's fixed" (shop hot-swap, fridge recovery)
[Nov 01]          ──> Sim 6: One-command demo + scripted timeline
[Nov 01 - Nov 02] ──> Sim 7: Wokwi ESP32 bonus (only if Sim 0–6 done)
```

This replaces Log Ingestion steps **I2–I4** in `roadmap.md`; I1 (upload/paste) and I5 (webhooks) stay there.

UI work runs in parallel under **🎨 UI: Incident Command Center** in `roadmap.md` (U0–U4). The shop tile, service map, and fridge built here become that screen's "World" column (U3); pipeline lanes become its incident cards (U1).

---

## Sim 0 — Plumbing *(Wed, Oct 28 · ~3 h)*

Small, backward-compatible changes so everything after it plugs in.

- [x] `core/schemas/remediation.py` → `RunRequest`: add `source: Literal["manual","upload","watcher","webhook"] = "manual"` and `target: Optional[Literal["inventory"]] = None`.
- [x] `apps/api/main.py` → `/api/run`: when `target == "inventory"`, load `demo/target-service/inventory.py` server-side as `original_code` (allowlisted; never accept a client file path).
- [x] Pass a PR opener bound to `code_path="inventory.py"`, `test_path="test_inventory_regression.py"` (e.g. `functools.partial(open_fix_pr, ...)`) for inventory runs.
- [x] New endpoint `POST /api/run/appliance/readings` taking `ApplianceTelemetry` (existing schema) → `run_appliance_loop` directly. Keep `/api/run/appliance` (generated window) for the old button.
- [x] `core/schemas/events.py`: add `SimEvent` (`kind`: `shop_order`, `shop_metrics`, `fridge_reading`, `watcher_trigger`, `fix_applied`; `payload: dict`) broadcast via `EventHub`.
- [x] `POST /api/sim/events` so out-of-process simulators (shop, watcher) can publish `SimEvent`s to the dashboard.
- [x] `AgentStep` gains `source` so the dashboard can badge "Detected by watcher".
- [x] `.env.example`: `GITHUB_DEMO_REPO`, `GITHUB_BASE_BRANCH`, `SHOP_PORT=8002`.
- [x] Tests: `target="inventory"` sends the real file as `original_code`; readings endpoint runs the loop with mocked models; `SimEvent` broadcast.
- Exit: `curl` with `target=inventory` runs fail-to-pass against the real `inventory.py`.

## Sim 1 — Real mini shop (S2) *(Oct 28–29 · ~6 h)*

A real app that really fails because of the real bug.

- [x] `demo/shop/app.py`: tiny FastAPI app on `:8002` ("AutoParts Lagos") with `GET /products`, `POST /orders` (moves stock between 2–3 items using `inventory.acquire_all` / `release_all`).
- [x] Load `inventory` from an **active module path** (default: `demo/target-service/inventory.py`), so Sim 5 can hot-swap to the patched copy without touching the buggy original.
- [x] Lock timeouts in the shop (not in `inventory.py`): a stuck acquire after N ms becomes `WARN lock wait … retry=n`, then `ERROR Deadlock detected … rolled back`. The laptop never freezes.
- [x] Structured log lines to `demo/shop/logs/shop.log` (same shape as `samples/database_deadlock.log`).
- [x] Publish `shop_order` (ok / waiting / failed + latency) and per-second `shop_metrics` (orders/min, error rate, p95) to `POST /api/sim/events`.
- [x] `demo/shop/load.py`: N concurrent shoppers with random item order; `--rate`, `--duration`, `--shoppers`.
- [x] Shop page in Next.js at `apps/web/app/shop/page.tsx`: product cards, **Buy** button, spinner, "Order failed" toasts, live error-rate sparkline (reads `SimEvent`s from the existing socket).
- [x] Tests: shop with the buggy module produces timeouts under load; with a sorted-order module it doesn't (stdlib threads, no models).
- Exit: running `load.py` makes orders visibly fail on `/shop` and writes real deadlock logs.

## Sim 2 — Log watcher (autonomous grab) *(Thu, Oct 29 · ~4 h)*

- [x] `core/watch/log_watcher.py`, run as `python -m core.watch.log_watcher --file demo/shop/logs/shop.log --api http://localhost:8001 --target inventory`.
- [x] Tail with rotation/truncation handling.
- [x] Trigger rules (`core/watch/rules.py`, shared with Sim 4):
  - Warning: ≥ 2 `retry=` on the same item within 30 s → early trigger.
  - Error: `Deadlock` / `ERROR` / `Traceback` → incident.
- [x] Context window: last 30 lines before + 10 after → `POST /api/run` with `source="watcher"`, `target="inventory"`.
- [x] Debounce by fingerprint (error type + resource) for N minutes: one retry storm = one run.
- [x] Publish `watcher_trigger` (rule, matched lines) so the dashboard shows *what* was grabbed.
- [x] Tests: rule matching, window, debounce, rotation (temp files, no network).
- Exit: start shop + load + watcher → a run starts with no clicks, verified against the real `inventory.py`.

## Sim 3 — Service map + pipeline lanes (S1) *(Fri, Oct 30 · ~5 h)*

- [x] `apps/web/app/components/ServiceMap.tsx` (SVG): Shoppers → Shop API → Inventory locks (`axle`, `brake-pad`, …) → Orders DB.
- [x] Each `shop_order` animates a dot: green ok, yellow waiting, red failed.
- [x] Deadlock view: two orders each holding one lock and waiting on the other, drawn as a red cycle between the two item nodes.
- [x] `apps/web/app/components/PipelineLane.tsx`: CRASH → GRAB → SUGGEST → VERIFY → FIX stepper, fed by `watcher_trigger` + existing `AgentStep`s (`diagnose`, `generate`, `verify`, `done`).
- [x] Badge from `AgentStep.source` ("Detected by watcher" / "Manual"); timer "first warning → verified fix".
- [x] Keep the current panels' `Stage` details below each lane (reuse `applyStep`).
- Exit: during a watcher run, the map shows the deadlock cycle and the lane advances step by step. ✅ Live probe 2026-10-27 (API :8011 + shop :8012): `shop_order`/`shop_metrics`/`watcher_trigger` all arrive over `/api/ws`; under load 216/216 failed orders with item lists reached the socket (deadlock-pair input); `npm run build` clean.

## Sim 4 — Virtual fridge (H1) + sensor watcher *(Oct 30–31 · ~6 h)*

Simple state model, not a physics simulator (keeps the Scope Rules).

- [ ] `core/simulate/fridge_stream.py`: `VirtualFridge` stepping every tick (1 s real = 1 simulated min), reusing `BASE_TEMP_C`, `BASE_CURRENT_A`, `BASE_VIBRATION_G` and the same fault names as `appliance.py`.
- [ ] State: `door_open`, `condenser_dirty`, `surge`, `short_cycling`, compressor on/off; faults and repairs change state, readings follow.
- [ ] Run inside the API as an asyncio background task; controls:
  - `POST /api/sim/fridge/fault` (`door_open`, `condenser_fouling`, `power_surge`, `rapid_restart`)
  - `POST /api/sim/fridge/action` (`close_door`, `clean_condenser`, `reset`)
  - Each tick broadcasts `fridge_reading`.
- [ ] `core/watch/sensor_watcher.py` (uses `rules.py`), evaluated on every reading:
  - Warning: temp > 5 °C for 3 readings (fridge) / > −15 °C (freezer), or current > 130 % baseline.
  - Error: temp > 8 °C, or current spike > 3× baseline.
  - On trigger: last 30 readings → `ApplianceTelemetry` → same path as `/api/run/appliance/readings`, `source="watcher"`. The fault name is **never** sent to the model.
- [ ] `apps/web/app/components/VirtualFridge.tsx` (SVG): door swing, interior light, compressor vibration when running, frost on a dirty condenser, flicker on surge; gauges for °C / A / g; live temperature chart; fault buttons.
- [ ] Hardware lane: CRASH → GRAB → SUGGEST → SAFETY (`validate_runbook` result) → FIX (alert + work order).
- [ ] Tests: each fault moves readings in the expected direction; watcher fires once per fault; the model payload contains no fault label.
- Exit: click **Open door** → temperature climbs on the chart → watcher triggers → runbook + work order appear, no other clicks.

## Sim 5 — "Proof it's fixed" *(Fri, Oct 31 · ~3 h)*

- [ ] Software: `POST /api/sim/shop/apply-fix` writes the **verified** `patch_code` to `demo/shop/.runtime/inventory_active.py` (gitignored) and tells the shop to reload its active module. Only allowed when the run status is `PASS`.
- [ ] The shop error rate falls to 0 and the service-map dots turn green; publish `fix_applied`.
- [ ] Mirror reality: the PR on GitHub is the durable fix; apply-fix stands in for "merge and deploy".
- [ ] Hardware: "Technician applies runbook" button maps safe steps to `/api/sim/fridge/action` (close door, clean condenser); the temperature curve returns to ~3.5 °C.
- [ ] Never auto-execute a step that `validate_runbook` would reject.
- [ ] Tests: apply-fix rejected for FAIL runs; reload uses the patched module; the buggy original is unchanged.
- Exit: both lanes end visibly healthy.

## Sim 6 — One-command demo *(Sat, Nov 1 · ~3 h)*

- [ ] `scripts/demo.sh` (or `npm run demo`): API `:8001`, web `:3000`, shop `:8002`, log watcher; the fridge runs inside the API.
- [ ] `demo/timeline.yaml`: e.g. 0:20 start shop load → 0:50 open fridge door; a "Play scenario" button in the dashboard.
- [ ] Reset button: clear runtime patch, reset fridge, clear the dashboard.
- [ ] Update `demo/script.md` shots to the new flow: shop failing → watcher → PR → shop green; fridge door → chart → work order → recovery.
- [ ] Pre-capture backup footage of a known-good run.
- Exit: from a clean clone with `.env`, one command plus one click plays the full scenario.

## Sim 7 — Wokwi ESP32 bonus (H2) *(Nov 1–2 · ~4 h, only if Sim 0–6 done)*

- [ ] `hardware/wokwi/`: `diagram.json` (ESP32, DS18B20 or DHT22 temperature sensor, push button = door switch, potentiometer = current sensor) + `sketch.ino`.
- [ ] Firmware posts readings as JSON to `POST /api/telemetry/appliance` (single reading → fed into the same `sensor_watcher` buffer as the virtual fridge).
- [ ] Networking: needs the public demo API URL, or Wokwi for VS Code with the private gateway for localhost.
- [ ] 15-second clip: press the "door" button on the virtual circuit → the hardware lane triggers. Line for the video: "the same firmware runs on a real ESP32."
- Exit: a reading from Wokwi reaches the dashboard and can trigger the watcher.

---

## ✅ Definition of done

- [ ] No manual "Inject" click needed: both incidents are grabbed by watchers.
- [ ] Software fix is verified **fail-to-pass against the real `inventory.py`** and opens a PR that changes it.
- [ ] Both systems visibly recover after the fix.
- [ ] Existing panels, endpoints, and the 79 tests still work.
- [ ] Every new module has unit tests that run without network or model keys.

## ⚠️ Risks and fallbacks

| Risk | Fallback |
| :--- | :--- |
| Deadlock timing is flaky under load | Seed shopper order; widen the timeout window; replay a recorded `shop.log` into the watcher |
| Modal cold start slows the live take | Warm the sandbox before recording; narrate over the verify step |
| SVG animation eats time | Ship lanes + gauges first; animation polish last |
| Wokwi networking blocked | Skip Sim 7; mention ESP32 in "Next version" |
| `GITHUB_TOKEN` / demo repo not ready | Show the verified patch diff in the dashboard; open the PR after recording |
