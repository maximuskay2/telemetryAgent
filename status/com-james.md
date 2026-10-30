# James status (commercial)
Current block: C-J2 next (Phase 1 API)
Done: C-J0 (f33e06c, tagged commercial-contracts-in), C-J1 (this commit)
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
Contract changes requested: none (§8 frozen at C-J0)
Live runs (lang · result · seconds · model): none this round
NEEDS FROM AKINGBADE:
- Clerk dev application: JWKS URL + test publishable/secret keys (dev only,
  no production keys this round).
- Railway Postgres for staging (+ DATABASE_URL), staging/prod environments,
  Railway volume for TA_DATA_DIR/uploads; provider spend caps; enable
  automated daily Postgres backups (staging + prod, ≥7 days).
- Baseten/Modal remaining hackathon credit numbers (for Jude's alerts).
- Confirm provider product-use terms (roadmap §0.1) when known.
BLOCKED: none
