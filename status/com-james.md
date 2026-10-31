# James status (commercial)
Current block: done — all C-J blocks on main (C-J4, hooks, C-J5 merged
  as e40c312; gate green on John's C-N9)
Done: C-J0 (f33e06c, tagged commercial-contracts-in), C-J1 (2baf475),
  C-J2 (8d6b046), C-J3 (c89c60e), C-J4 (9404eba), model_call hooks
  (8dcdcc6, Jude's NEEDS closed), C-J5 (6c65e3b) — all on main,
  check.sh GREEN (python 1070 + smoke + web + flutter)
Decisions:
- Auth provider: Clerk (dev instance, test keys). Provider proves identity
  only (sub + email); our memberships table owns orgs + roles, so we stay
  provider-portable. JWKS JWT verify; tests use local HS256 issuer, no net.
- DB driver: psycopg (sync via asyncio.to_thread, matching today's style).
- Secrets: Fernet envelope, per-org data key wrapped by COMMERCE_MASTER_KEY.
- usage_events gains `model` (cost table is per provider+model); allowances
  counters bump in the usage-insert transaction.
- Demo channel: VetoRing approves sim runs from Mission Control, so demo
  reads (actions/runs/gate/systems GETs) stay public-but-scoped and
  approve/disapprove on in-memory sim runs needs no auth in either mode.
  Self-hosted keeps today's behaviour exactly.
- Rebased probe note 90a0686 is on main; post-rebase full suite re-run on
  origin/main is 933 green — the single earlier failure was a flake.
- C-J0 gate flaked twice on a docs-only tree (rotating victims: e2e
  python/php NO_ACTION drafts, devices_e2e 10 s timing, smoke, flutter);
  matrix module alone is 7/7 PASS and the third gate run is GREEN —
  load/timing flakes in Docker-backed tests, not this commit. Jude may
  want to harden test_lang_e2e timeouts (his file).
- C-J1 DONE: core/commerce (db, schema.sql, repo PG+file, models,
  crypto) + tests/commerce_db.py + tests/test_com_core.py (20 tests) +
  boot hook + docs/ops-backups.md + psycopg/cryptography pins.
- C-J1 RLS lessons: superusers bypass RLS, so prod/dev/test use
  least-privilege roles (ta_app/ta_test via ensure_app_role); key→org
  lookups are SECURITY DEFINER functions (can't set app.org_id before
  resolving it); PG checks the SELECT policy on INSERT…RETURNING, so
  create_org pairs with the owner membership; SQL function args must not
  collide with column names. ensure_schema is hash-versioned + fully
  idempotent. Local ta-postgres on 5432 with ta_james/telemetry_test.
- Next: C-J2 (JWT middleware + org/member/invite/device routes). Jude:
  tests/commerce_db.py fixture + repo.record_usage_event/
  list_usage/get_allowance are ready for C-D1/D2 (usage.py still yours).
- C-J1 rebased on Jude's C-D1/D2/D3 (4820876, no collisions); 86
  commerce tests green together (20 C-J1 + 25 com_usage + 41 usage).
  Jude C-D4 note: your record_usage writes the core/usage engine store;
  my repo.record_usage_event is the §8.3-table primitive — C-D4 must
  reconcile the two (engine read-model vs tables, or persist-through).
  Also create_org now pairs the owner membership (RLS RETURNING rule).
- C-J2 DONE: core/commerce/auth.py (Clerk JWKS verify + test HS256
  issuer, PUBLIC_PATHS, resolve_request, role/authorize helpers),
  apps/api/routes/commerce.py (exact §8.4 JSON: orgs, members, invites,
  transfer, pair/claim/devices/revoke, usage→Jude's summary, admin),
  middleware + approve/disapprove/pause/execute dual rules (self-hosted
  unchanged; hosted demo runs public, org runs member+/admin+),
  tests/test_com_api.py (17) + tests/commerce_auth.py, PyJWT pin, docs.
  103 commerce tests green (20+17 mine, 66 Jude's).
- C-J2 notes: RLS reads inside resolve_request need scoped stores
  (unscoped hides everything); middleware added BEFORE CORS so error
  responses keep CORS headers; GET pause stays public (only the action
  is gated); WS keeps today's behaviour until C-J3's token join.
- Merged 8d6b046 (C-J1+C-J2 over John's C-N3..C-N5, zero shared files);
  John's 8201 freed so the devices e2e gate is reliable again.
- C-J3 DONE: org_id through mitigate/run/github/ingest/pipeline,
  per-org EventHub channels + WS token join (device tokens join own org,
  cross-org refused 4403), org-scoped device routes (system-key auth,
  queue-link + ack checks), sensor/ingest path org-aware (profiles via
  repo, gate/watcher/appliance runs tagged), run/action broadcasts via
  emit_for, /api/actions demo leak closed (per-run visibility),
  create_org pins ids + import_connection (hash-preserving),
  core/commerce/migrate.py + scripts/commerce-migrate.py (profiles/
  connections/pause/rate/audit into `legacy`, demo stays in files,
  idempotent), tests/test_com_migrate.py (5) + tests/test_com_isolation.py
  C-J3 rows (RLS direct-SQL bypass over 6 tables, pause A/B, WS join +
  fan-out). Live Clerk wiring proven: JWKS fetch, real session JWT
  verifies to clerk|…, email backfill True, garbage 401; probe users
  deleted. Found + fixed: CLERK_API_URL tolerates a bare host (no /v1).
- C-J3 test notes: test_prod_repofix in-flight seed uses the new
  (org, fingerprint) key (same assertion); gate-candidate tests mock
  run_agent, so untagged gate runs keep calling it (scoped impl only
  for org-tagged runs) — no test rewrites.
- C-J4 DONE (5a23bcf): 10-test two-org matrix (org/system/connection/
  run/action/option/decision/device/ingest/pause/admin — B reaches
  nothing of A's by ID or guessing; A's-key ingest lands in A only).
  Hardening the matrix found: cross-org run access is 404 (was a 403
  oracle); revoke checks membership before resolving the token;
  first device poll with pending commands refuses (execute needs a
  link, so pending-without-link is always foreign); PG connection
  rows normalize last_seen NULL→0.0 (was a 500 on create/list).
  Note for later: baseline_learners/signal_watches/_RUN_FIRST_SEEN
  are keyed by bare system_id — same-slug systems across orgs would
  share in-memory learner state (not in C-J4's brief; sessions carry
  org tags and observe/progress enforce them).
- Hooks DONE (9c364d1, Jude's NEEDS closed): model_call in/out via
  Kind + record_usage in generate_json/repro/patch/choose_files,
  threaded from run.py (org/system/run/language); chars/4 estimate
  (thin clients report no usage; real OpenAI usage left for later);
  skipped when untagged/demo; cost table already covers both models.
  Jude: engine-file rule is org-gated, NOT hosted-gated (unlike my
  run.py _usage) so file-store C-D4 proofs record too.
- C-J5 DONE (5cbbaad): GET export (owner; hashes + sealed secrets
  travel, token hashes excluded), POST restore (pinned id, members
  re-attach by external id, keys keep working), POST purge after
  30-day delete grace (all org rows gone, user rows survive by
  design — RLS has no users-DELETE policy), sweep fns + script with
  floors (7d audit, 5 versions), 5 tests incl. full round-trip.
  Restore drill PASS (local pg_dump/restore + API boot + RLS read),
  logged in docs/ops-backups.md; staging drill NEEDS Akingbade.
Contract changes requested: none (§8 frozen; John's 8201 freed — the
  free-port hardening suggestion for test_devices_e2e.py stands as a
  nice-to-have in his court)
Live runs (lang · result · seconds · model): none this round
Clerk wiring: LIVE (dev app; JWKS + secret + API URL received and
  verified end-to-end; users cleaned up). No production keys in use.
NEEDS FROM AKINGBADE:
- Railway Postgres for staging (+ DATABASE_URL), staging/prod environments,
  Railway volume for TA_DATA_DIR/uploads; provider spend caps; enable
  automated daily Postgres backups (staging + prod, ≥7 days).
- Baseten/Modal remaining hackathon credit numbers (for Jude's alerts).
- Confirm provider product-use terms (roadmap §0.1) when known.
- Tuning (Akingbade ask): baseline learning window 120s → 30s demo
  (`DemoLearnIn` default + `/api/demo/.../learn` fallback), 120s → 60s
  production (`BaselineStartIn` default). No test depended on 120.
FLAG FOR JOHN: web copy still says "Two quiet minutes" (start/setup
  page.tsx:687, start/page.tsx:83) — now 30s in demo. Your files.
  (Also: Akingbade asked me to fix FridgeTile Faults/Fix dropdowns
  directly — replaced the overlay menu with in-flow option chips;
  John's file, minimal diff, build green. Shout if you want it back.)
- Fix (gate): smoke_demo.sh now unsets DATABASE_URL — .env gained one
  and the sim-without-DB proof was booting hosted (401s). Smoke green.
BLOCKED: none (8201 saga over — John's C-N9 made the devices e2e
  free-port, so the gate can never block on a squat again; the one-off
  check7 suite crash `can't open file '.../python -m unittest'` never
  reproduced across 3 further full runs and no in-repo spawner exists —
  treating as environmental one-off, watching).
