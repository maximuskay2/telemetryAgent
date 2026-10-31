# Commercial ops: environments, secrets, backups (C-J1)

How the hosted product is configured and kept safe. Code: `core/commerce/`
(schema in `core/commerce/schema.sql`, applied at boot when `DATABASE_URL`
is set). Self-hosted installs (no `DATABASE_URL`) need none of this — the
file store runs everything, exactly as before.

## Environments (NEEDS Akingbade — no Railway access for agents)

Two Railway environments, each with its own Postgres + model keys:

| | staging | production |
|---|---|---|
| Purpose | pre-merge proving, pen-test checks | real (free) customers |
| Database | Railway Postgres `telemetry-staging` | Railway Postgres `telemetry-prod` |
| Model keys | separate keys, spend caps | separate keys, spend caps |
| Uploads volume | Railway volume → `TA_DATA_DIR` | Railway volume → `TA_DATA_DIR` |

Uploaded documents stay on disk (`TA_DATA_DIR/uploads`), so each
environment needs a volume. Everything else org-scoped lives in Postgres.

## Environment variables (per environment)

| Var | Where | Notes |
|---|---|---|
| `DATABASE_URL` | Railway Postgres | **App role URL, not the superuser URL.** Superusers bypass RLS. Create `ta_app` once per database (below) and point the service at it |
| `COMMERCE_MASTER_KEY` | Railway secret | base64 32-byte Fernet key; wraps every org data key. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Rotate = re-wrap drill (not yet run) |
| `COMMERCE_ADMIN_EMAILS` | Railway variable | comma list; `GET /api/admin/costs` 403s everyone else |
| `CLERK_JWKS_URL`, `CLERK_SECRET_KEY` | Railway secret | C-J2; dev/test keys only this round |
| `PORT` | Railway injects | already honoured |
| `TA_DATA_DIR` | volume mount | uploads + (self-hosted) the file store |

Self-hosted keeps `CONNECT_ACCESS_CODE` / `MOBILE_API_TOKEN`; hosted
ignores them.

## Database roles (run once per database, as the bootstrap superuser)

```python
from core.commerce import db
db.ensure_schema("postgresql://postgres:...@.../telemetry")
db.ensure_app_role("ta_app", "<strong password>", "postgresql://postgres:...@.../telemetry")
# then set DATABASE_URL=postgresql://ta_app:<pw>@.../telemetry on the service
```

Re-run `ensure_app_role` after schema changes (grants cover existing
tables + sequences). `ensure_schema` is hash-versioned: it re-runs
`schema.sql` (idempotent) only when the file changed; the app role boots
read-only against a current schema.

## Local dev Postgres (each agent)

```bash
docker run -d --name ta-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
docker exec ta-postgres psql -U postgres -c "CREATE DATABASE ta_james;" -c "CREATE DATABASE telemetry_test;"
```

Then, once per database, `ensure_schema` + `ensure_app_role("ta_app", ...)`
as above (James: `ta_james`; John: `ta_john`; Jude: `ta_jude` — create your
own database). Dev `DATABASE_URL` uses the `ta_app` role. Tests use
`TEST_DATABASE_URL` (default `postgresql://postgres:postgres@localhost:5432/
telemetry_test`, bootstrap role) and exercise RLS through the `ta_test`
role the fixture creates; DB tests skip when Postgres is unreachable.

## Backups (NEEDS Akingbade)

- Enable Railway automated daily Postgres backups on staging + production,
  retention ≥ 7 days.
- Restore drill (C-J5 runs it, result logged below): restore the staging
  backup into a scratch database, boot the API against it, check
  `/api/health` + one org login. Pass = drill log entry here.

### Drill log

- 2026-10-31 (James, C-J5) — PASS (local). Seeded `ta_james` with one
  org + user + membership + system, `pg_dump -Fc` → fresh `ta_drill`
  → `pg_restore` exit 0, row counts identical (orgs/users/memberships/
  systems/systems_versions/connections/audit 1/1), all 6 DEFINER
  functions present (4 resolvers + 2 sweep). `ensure_app_role` on the
  restored DB, then booted the API against it as `ta_app`:
  `GET /api/health` 200, RLS-scoped repo read returned the drill org
  (owner) + system, authed `GET /api/orgs` 200. Scratch DB, dump, and
  seed deleted after. Note: restore into a non-empty DB fails loudly
  (87 already-exists errors) — always restore into a fresh database.
  Staging drill with Railway backups + real Clerk login still NEEDS
  Akingbade (no Railway access for agents).
