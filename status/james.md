# James status
Current block: J-R0 real connections store + ta_live_ keys (next)
Done: H0 contracts + stubs + check.sh (sha filled at next checkpoint)
Decisions (ambiguities I resolved):
- H0: stub POST /api/connections echoes the request's system_id/kind onto the fixture connection and returns key "ta_live_fixture" (the key the H0 auth stub accepts).
- H0: stub GET /api/incidents/{run_id}/options echoes the path run_id with domain "software".
- H0: fixture scalars follow §3.4 examples (con_ab12, acme-api-9f2c, ****abcd, 1730200000.0, cmd_1/defrost/1730200120); shapes match §3.4 exactly.
- H0: no POST /api/devices/{id}/readings stub — its shape is not in §3.4, so John defines it in N-R1 (his file after the tag).
- H0: routers don't import apps.api.main (no broadcasts in stubs); main.py H0 diff is imports + 2 include_router lines at the end only.
- H0: check.sh python = venv/bin/python, else ../telemetry-agent/venv/bin/python, else python3 (worktrees have no venv of their own).
- H0: smoke_demo.sh checks web pages only when SMOKE_WEB_URL is set — §9.0 forbids touching live :3000, so there is no default; John can point it at :3201.
- H0: smoke_demo.sh sources ../telemetry-agent/.env for model keys and always unsets GITHUB_TOKEN/GH_TOKEN so smoke can never open a real PR.
- H0 gate: check.sh steps 1-3 GREEN (498 python tests, smoke incl. 2 live agent runs, web build). Step 4 flutter has 3 failures PROVEN pre-existing (identical on pristine main, mobile tree untouched, John's files) — John's N-R0 fixes them. H0 merges with this documented exception; blocking it would deadlock John's start (he needs the contracts-in tag).
Contract changes requested: (none)
NEEDS FROM AKINGBADE: (none yet)
BLOCKED: (none)
