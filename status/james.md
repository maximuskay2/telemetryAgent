# James status
Current block: T-R1 backend half (proof support; John's N-R3/N-R4 in flight)
Done: H0 (7bb037b), J-R0 (134af27), J-R1 (65a88cb), J-R2 (bdb2bd4), J-R3 (36aaa4f), J-R4 (8157049), J-R5 proof app + docs (this commit)
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
- J-R0: third-party secrets (github/railway/webhook) rest recoverable in the mode-600 file — hashes would make outbound calls impossible. Only secret_hint leaves the API. Matches §7 "hashed keys, masked tokens, file mode 600".
- J-R0: create → 404 for unknown systems, except the fixture system when TA_FIXTURE_KEYS=1 (John's stub-phase device tests). github/railway/webhook without secret → 400.
- J-R0: test endpoint does stored-config checks now; github returns ok:false "live checks land in J-R2" (honest, not green). Live github checks in J-R2, hosting checks with the J-R4 adapters.
- J-R1: forwarder ships raw lines; the server owns traceback reassembly (per system+service buffer, 30 s stale flush, 200-line cap) so cross-batch splits still become 1 candidate.
- J-R1: production candidates evaluate in-process; an act is recorded/broadcast but starts no run (log lines carry no metrics so act is unreachable; J-R3 wires production acts). Non-production hits delegate to the existing candidate endpoint for identical demo behaviour.
- J-R1: ingest decision bodies add "window" (capped 4000 chars) so J-R3 re-parses frames from run["gate"]; the existing candidate body is untouched.
- J-R1: connection_status fires only on waiting→ok transitions for real connections (fixture traffic skips it — no record to mark).
- J-R1: forwarder forwards WARNING+ plus full tracebacks (--level tunable), tails from end, survives rotation/truncation, buffers in memory (cap 20000, oldest drops) with backoff 1→60 s; 401 batches are reported + dropped (a bad key never recovers). Durable spool is future work.
- J-R1: Sentry fixture at tests/fixtures/sentry_issue.json (exact §4 name, not prod_-prefixed).
- J-R2: no github_pr.py change was needed — open_pr/open_fix_pr already accept repo/token params; the new resolver is core/connections/github.connection_repo (repo, base, token for J-R3).
- J-R2: write probe = create + immediately delete a throwaway ta-probe-* ref (no trace). Read-only → ok:false "can read, cannot open PRs" (the fix flow needs PRs, so the test is red).
- J-R2: default branch travels in the detail string ("connected · default branch main · ...") — no contract change needed since ConnectionTest has no branch field.
- J-R3: trigger is parse-based, not rule-based (a traceback mentioning "deadlock" matches the deadlock rule but still triggers; plain ERROR lines stay candidates). Traceback rule only in effect.
- J-R3: ingest auto-triggers (armed + production + github conn + parsed traceback + fingerprint not in flight). NO new endpoint — tests call run_repo_fix directly, keeping §3.4 untouched.
- J-R3: one-PR-per-fingerprint via deterministic branch telemetry-agent/fix-<fp12>; existing open PR → "seen again" comment. Repeat comments throttled to 1/hour/fingerprint.
- J-R3: patch >3 files → keep first 3 + note in PR body. Unknown paths dropped; no known paths → attempt fails.
- J-R3: draft PR (NO_ACTION + pr_url) for: locate fails, snapshot >50 MB, pip fails, no tests, repro won't fail, patch won't prove. Draft carries TELEMETRY_AGENT_DIAGNOSIS.md (+ repro test when one failed). Only "no sandbox" is a hard FAIL.
- J-R3: Modal upload is chunked base64 exec (no secrets inside ever); Modal setup failure of ANY kind falls back to Docker; clear error names both when neither works.
- J-R3: ExecutionResult gained §3.4-sanctioned additive fields repo/suite/mitigation (John reads pr_url/repo/suite from GET /api/runs/{id}.result).
- J-R3: Wonder escalation lives in core/repo_fix/generate.py (own OpenAI stanza) — core/infer is not James's to edit.
- J-R3 live proof: PR #9 (sorted fix, fail→pass, 5 passed/0 new), ×5→1 PR + comment, draft #10 verified + closed. Only #9 left open (deliberate proof PR).
- J-R4: adapters live INSIDE mitigate.py (R-2: only listed files) — Railway GraphQL + signed webhook.
- J-R4: gates order allowlist → paused → learning → rate → policy (proposals only; explicit human taps bypass policy) → connection. Only DONE runs consume the rate budget; failures retry immediately.
- J-R4: mitigation windows are mitigate-owned (separate dict; main's apply dispatch is frozen) reusing PendingAction + action_pending/tick/resolved so John's app needs no new WS code. Lazy ticker; tests drive settle_due manually.
- J-R4: proposals are approve-to-run (auto_apply=False) — nothing runs by itself with no error-rate feed. Repo-run start proposes rollback (policy-gated, silent skip); T-R1 phone rings from this.
- J-R4: software_options always lists rollback/restart (safety-gated with reasons) + open_pr when pr_url exists. Ids opt_<action>; action_for_option_id parses for John's router. execute("open_pr") → noop.
- J-R4: Railway shapes from public docs (deployments list, deploymentRedeploy, deploymentRestart, me) — implemented + mocked, NOT live-verified (no token here).
- J-R4: rollback = redeploy newest SUCCESS deployment (even if it is the latest, with note); restart = deploymentRestart on latest.
- J-R5: proof app = cart service, empty-cart ZeroDivisionError, 20 green tests, Procfile + trigger_bug.py + forwarder line. Traceback verified live (app/cart.py:37). No try/except on purpose — the crash must reach the logs.
- J-R5: DOCUMENTATION.md got exactly the two link lines (§17); production-devices.md link dangles until John's doc lands.
- Note for John: test_software_options_empty_until_jr4 now fails because J-R4 IS on main (software_options returns 2 safety-gated options by design). Your file, your call — the "until R4" expectation has flipped.
- J-R5 gate: python 619/620 (only John's stale test above), smoke GREEN, web GREEN, flutter 45/45 GREEN on the identical mobile tree earlier (this run's step 4 waited on John's concurrent flutter lock; J-R5 touches no mobile code). Merged with these two documented exceptions.
Contract changes requested: (none)
NEEDS FROM AKINGBADE: create public maximuskay2/telemetryAgent-proof-app from examples/proof-app/ + deploy on Railway; RAILWAY_TOKEN + staging service id for live mutation verify
BLOCKED: (none)
