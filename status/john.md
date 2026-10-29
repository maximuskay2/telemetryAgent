# John status
Current block: N-R3 Flutter action center (next)
Done:
- N-R0 verify (d046878): 3 stale widget tests fixed (tall surface; stale copy),
  analyze clean, 32 flutter tests green, debug APK builds
- N-R0 scaffold (5d211bc): action cards + 5 widget tests (37 flutter green)
- N-R1 core (8d57477): core/devices options builder + queue, 23 python tests
- N-R2 sim (e0e08ca): sim_device.py + 5 protocol tests (fake API)
- Rebased on origin/main 7bb037b (contracts-in tag received)
- N-R0 mirror: §3.4 → apps/mobile/lib/models/production.dart
  (+ 8 parse tests) and apps/web/app/types/production.ts (web build green)
- N-R1 router: real devices.py (options/execute/queue/readings) + 16 router
  tests; James's 3 stub-pinning tests updated to real behavior (see Decisions)
- N-R2 e2e + firmware: sim vs live 8201 green in ~3s; sketch polls commands,
  drives COMP/DEFROST/BACKUP LEDs, diagram + README updated
Decisions (ambiguities I resolved):
- Worktree branched from origin/main @ 0cd9447 (roadmap names 21246cd; moved one
  roadmap-only commit; no code impact). No merge to main yet: check.sh did not
  exist until James's H0; first merge at this checkpoint.
- N-R0 test failures (3, red since 2da7d13): fixed in tests, not product. The 340px
  CountdownRing fills the default 600px test surface's list viewport, so below-fold
  content is offstage to default finders; gave the two alarm widget tests the tall
  (800x4000) surface already used by report_test.dart. Updated the stale
  'Collecting live temperatures' expectation to the shipped 'Collecting live readings'
  copy (widget renamed in 2da7d13 when charts went multi-sensor).
- Run→system link for options: entry["gate"]["system_id"] (gate payload carries it);
  profile=None degrades to hard-bounds-only checks. No frozen-file edits needed.
- options.py fail-closed rules: remote/manual need a runbook passing validate_runbook;
  power-cycle time-gated on started_at (my readings route will stamp it), refused when
  unknown; setpoint re-validates a runbook copy at the new target; dispatch always ok.
- Device command queue is in-memory (commands expire in 2 min), mirroring the run
  stores; option ids are deterministic slugs (opt_defrost, opt_manual_N, …) so the
  router rebuilds rather than stores them.
- sim_device device-side safety: compressor restart scheduled (never rushed),
  power_cycle refused during defrost, unknown actions nacked, acked ids deduped.
- Readings body (James left the shape to me, status/james.md): TelemetryIngestIn
  fields minus source_id (path device_id) and system_id (device key); the route
  delegates to the existing ingest handler (no duplication, no frozen edits).
- James's 3 stub-pinning device tests in tests/test_prod_contracts.py MUST be updated
  when the real N-R1 router lands (stub echo → real behavior + 404s); leaving them
  would fail check.sh and deadlock the merge. Minimal diff to those 3 tests only,
  everything else in his file untouched. Logged here per R-2 (cannot ask; roadmap
  mandates both the behavior change and a green gate).
- Tooling quirk: literal "Bearer <token>" strings in written files get redacted to
  "[REDACTED]" on disk; tests use placeholder keys (device-key-1), split asserts,
  and f"Bearer {FIXTURE_KEY}" (proven safe: no literal token on disk).
- N-R1 router: unknown run/option/command → 404 (codebase convention); unsafe or
  paused execute → 409; manual/dispatch resolve at once; open_pr execute is a
  done no-op (phone opens the URL); rollback/restart delegate to
  mitigate.execute; remote re-validates then queues. Commands GET withholds while
  paused. Started_at anchor = entry stamp, else first-view cache (AgentStep has
  no timestamps). Execute resolves the device from sightings (latest readings/
  poll per system); none seen → 409. option_status broadcast on every outcome.
- N-R2: e2e seeds its run (no model keys in tests); full fault→run→options chain
  is proof-run territory. Sketch compile is a human Wokwi check (see NEEDS).
Contract changes requested: —
NEEDS FROM AKINGBADE:
- Compile the N-R2 sketch.ino + diagram.json in Wokwi (no Arduino toolchain here);
  if the LED/resistor part names need adjusting, note it in status/john.md reply.
BLOCKED: —
