# TelemetryAgent

TelemetryAgent is a software-first autonomous SRE agent built for the
[Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details)
(Indie Developer track, Push the Frontier).

It ingests a crash log, finds the root cause with **Muse Spark**, writes a code
patch and a regression test with the open-weight **Muse Spark Open**, proves the
fix by running the test in an isolated **Modal Sandbox**, retries with the
failure output when verification fails, and opens a **GitHub pull request** once
the fix passes.

The same reasoning core also handles **appliance telemetry** (temperature,
current, vibration from a fridge or freezer) as a proof point beyond software:
it classifies the anomaly, writes a diagnostic runbook, checks it against
deterministic safety rules, and raises an alert and work order.

## Architecture

```text
   [ Software crash log ]            [ Appliance sensor window (synthetic) ]
             └──────────────┬──────────────┘
                            ▼
          muse-spark-1.3 (Meta Model API) — classify + diagnose
                            ▼
   meta-models/muse-spark-open on Baseten
   (backup: Fireworks → muse-spark-1.3)
     software → patch + pytest        appliance → runbook
                            ▼
     software → pytest in Modal       appliance → safety rules
                            │
              FAIL ─────────┴───────── PASS
                ▼                        ▼
   retry with feedback (max 3,     software  → GitHub PR
   last try on muse-wonder-1.0)    appliance → alert + work order
```

Every step streams to a Next.js dashboard over WebSockets.

## Interfaces

- **Web dashboard (main product):** a Next.js app in the browser where engineers
  watch both incident panels live.
- **Mobile extras (next version):** a phone-friendly alert page and a small
  owner-facing alert screen for the appliance path. These are planned for after
  the core build is complete; see [`roadmap.md`](./roadmap.md).

## Meta models and partners

| Role | Model | Provider |
| --- | --- | --- |
| Diagnosis and classification | `muse-spark-1.3` | Meta Model API |
| Patch, test and runbook generation | `meta-models/muse-spark-open` | Baseten |
| Generation backup | Muse Spark Open | Fireworks |
| Final-attempt escalation | `muse-wonder-1.0` | Meta Model API |
| Sandbox verification | — | Modal Sandboxes |
| Development | Muse Code | `muse` CLI |

## Status

The repository was started fresh for the hackathon, so all code in it is built
during the event (Oct 27 – Nov 4, 2026). See [`roadmap.md`](./roadmap.md) for
the day-by-day plan and [`about.md`](./about.md) for the technical blueprint.

### Built during the hackathon

This list is updated as features land.

- Project plan aligned with the hackathon requirements (`about.md`, `roadmap.md`).
- Typed software/appliance telemetry, diagnosis, patch/runbook and stream-event contracts (`core/schemas/`).
- Diagnosis via `muse-spark-1.3` on the Meta Model API (`core/infer/meta_client.py`, `/api/diagnose`).
- Patch generation on Muse Spark Open with Baseten → Fireworks → Meta failover (`core/infer/`).
- Modal Sandbox pytest verification with fail-to-pass checks (`core/verify/sandbox.py`).
- Shared diagnose → generate → verify → act loop with `muse-wonder-1.0` final-attempt escalation, per-stage durations and real GitHub PR creation (`core/agent/loop.py`, `core/actions/github_pr.py`).
- FastAPI ingestion, `/api/run` agent endpoint and WebSocket streaming of every loop step (`apps/api/main.py`).
- Seeded deadlock fixture as the end-to-end PR target (`demo/target-service/`, `samples/`).
- Dashboard with software + appliance incident panels, inject buttons and a live event feed (`apps/web/`).
- Appliance path: synthetic fridge/freezer telemetry with injectable faults (`core/simulate/appliance.py`), runbook generation, deterministic safety validation (`core/verify/safety_rules.py`) and SMS/work-order alerts (`core/actions/notify.py`) through the same loop.
- Log ingestion: dashboard upload/paste with sample loader, allowlisted target files so verification is fail-to-pass against the real buggy file, and an autonomous log watcher (`core/watch/`) with warning/error/crash triggers, context windows, and per-fingerprint debounce.
- Live demo service under concurrent load plus a one-command autonomous demo (`demo/target-service/run_service.py`, `demo/live.sh`).

## Requirements

- Python 3.9+
- Node.js 20.9+
- npm

Setup and run instructions are added here as the API, agent loop and dashboard
land.

## Configuration

Credentials live in `.env`, which is git-ignored. Never commit keys.

| Variable | Purpose |
| --- | --- |
| `MODEL_API_KEY` | Meta Model API (Muse Spark, Muse Wonder) |
| `BASETEN_API_KEY` | Muse Spark Open on Baseten |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | Modal Sandboxes |
| `GITHUB_TOKEN` | Opening pull requests on the demo target repo |
| `FIREWORKS_API_KEY`, `FIREWORKS_PATCH_MODEL` | Optional backup generation provider |

Do not send sensitive log content to remote services.

## License

MIT; see [LICENSE](./LICENSE).
