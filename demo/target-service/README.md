# Demo target service

A small inventory-locking module with a seeded, reproducible bug: lock-ordering
inversion. It is the end-to-end fixture for the software loop.

## How the agent uses it

1. A deadlock log from `samples/` goes into the loop as `SoftwareTelemetry`.
2. The agent generates a patch + pytest suite.
3. Verification runs the generated test against this file as the **original**
   (must FAIL) and against the generated patch (must PASS).
4. A passing fix becomes a real PR on the demo-target repo (Day 4).

## Invariants

- `inventory.py` is the buggy original and must stay buggy. `tests/test_demo_fixture.py`
  pins the seeded behavior; if that test goes red, the fixture was disturbed.
- Stdlib only — no third-party imports — so the file runs unmodified in the
  Modal Sandbox image, which installs just pytest.

## Run the suite

```bash
cd demo/target-service
python test_inventory.py   # red while the bug is seeded: canonical-order test fails
```
