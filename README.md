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
   meta-models/muse-spark-open-1026 on Baseten
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

## Meta models and partners

| Role | Model | Provider |
| --- | --- | --- |
| Diagnosis and classification | `muse-spark-1.3` | Meta Model API |
| Patch, test and runbook generation | `meta-models/muse-spark-open-1026` | Baseten |
| Generation backup | Muse Spark Open | Fireworks |
| Final-attempt escalation | `muse-wonder-1.0` | Meta Model API |
| Visual symptom confirmation (optional) | `sam-3.1` | Meta Model API |
| Sandbox verification | — | Modal Sandboxes |
| Development | Muse Code | `muse` CLI |

## Status

The repository was started fresh for the hackathon, so all code in it is built
during the event (Oct 27 – Nov 4, 2026). See [`roadmap.md`](./roadmap.md) for
the day-by-day plan and [`about.md`](./about.md) for the technical blueprint.

### Built during the hackathon

This list is updated as features land.

- Project plan aligned with the hackathon requirements (`about.md`, `roadmap.md`).

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
| `MODEL_API_KEY` | Meta Model API (Muse Spark, Muse Wonder, SAM 3.1) |
| `BASETEN_API_KEY` | Muse Spark Open on Baseten |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | Modal Sandboxes |
| `GITHUB_TOKEN` | Opening pull requests on the demo target repo |
| `FIREWORKS_API_KEY`, `FIREWORKS_PATCH_MODEL` | Optional backup generation provider |

Do not send sensitive log content to remote services.

## License

MIT; see [LICENSE](./LICENSE).
