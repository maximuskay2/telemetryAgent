# James status (commercial)
Current block: C-J0 (this commit)
Done: C-J0 (this commit)
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
Contract changes requested: none (§8 frozen at C-J0)
Live runs (lang · result · seconds · model): none this round
NEEDS FROM AKINGBADE:
- Clerk dev application: JWKS URL + test publishable/secret keys (dev only,
  no production keys this round).
- Railway Postgres for staging (+ DATABASE_URL), staging/prod environments,
  Railway volume for TA_DATA_DIR/uploads; provider spend caps.
- Baseten/Modal remaining hackathon credit numbers (for Jude's alerts).
- Confirm provider product-use terms (roadmap §0.1) when known.
BLOCKED: none
