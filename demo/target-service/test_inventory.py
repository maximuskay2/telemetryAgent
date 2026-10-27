"""Minimal suite for the demo target service.

Plain asserts, no third-party imports: collected by pytest in the sandbox and
runnable directly with `python test_inventory.py`.
"""

from inventory import acquire_all, release_all


def test_single_item_roundtrip():
    held = acquire_all(["widget"])
    try:
        assert [name for name, _ in held] == ["widget"]
    finally:
        release_all(held)


def test_acquire_all_uses_canonical_order():
    held = acquire_all(["brake-pad", "axle"])
    try:
        assert [name for name, _ in held] == ["axle", "brake-pad"]
    finally:
        release_all(held)


def test_release_all_releases_locks():
    release_all(acquire_all(["axle"]))
    held = acquire_all(["axle"])
    try:
        assert [name for name, _ in held] == ["axle"]
    finally:
        release_all(held)


if __name__ == "__main__":
    failures = 0
    for name in sorted(n for n in globals() if n.startswith("test_")):
        try:
            globals()[name]()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
        else:
            print(f"PASS {name}")
    raise SystemExit(1 if failures else 0)
