# Demo rehearsal checklist (live judging)

The judged path (`/welcome` → `/start` → `/start/setup` → `/start/phone`
→ `/?tour=1` → wrap-up) is fully anonymous — Clerk can be down and the
demo still works. What CAN break it is listed below with the recovery.

## Freeze protocol

- No pushes to `main` during the judging window. Every push redeploys
  the API on Railway, and **a redeploy wipes in-memory demo runs**.
- No Railway variable changes (they redeploy too).
- No demo-reset clicks once the judged run starts.

## T-30 min: health

- [ ] `GET /api/health` → 200.
- [ ] `GET /api/infer/status` → `meta_catalog` non-empty (if empty,
      extraction still works via Baseten failover — note it, don't block).
- [ ] `/welcome` loads, no console errors besides the Clerk dev-keys
      notice (judged path doesn't touch Clerk).
- [ ] Android phone charged, paired, Test alarm rings once.

## T-10 min: fresh state

- [ ] `/start/setup` → Reset world (or restart the API for a clean slate).
- [ ] Walk stages 1–4 once yourself; confirm both systems arm.
- [ ] Close old `telemetry-agent/fix-*` PRs on `telemetryAgent-demo`.

## During: failure → recovery

| Symptom | Cause | Recovery (on camera) |
| --- | --- | --- |
| Extraction 502s | Meta blind window | Say "watch the failover", retry once — Baseten takes it |
| Demo resets to setup | API restarted/redeployed | Re-run `/start/setup` (~1 min), continue |
| Tour shows setup, not mission | Nothing armed | Finish arming both systems first |
| Phone silent | Foreground service asleep | Open the app once, re-run the incident |
| Paste/train 401 (production route) | Stale token | Reload the page (fresh token), retry |

## After

- [ ] Note anything that flaked, with timestamps, for the post-mortem.
- [ ] Only then resume pushing to `main`.
