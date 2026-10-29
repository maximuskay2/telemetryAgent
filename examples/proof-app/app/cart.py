"""Cart pricing for the proof shop.

BUG (for TelemetryAgent to find): `summary()` divides by `len(items)` when
computing the average item price, so checking out an EMPTY cart raises
ZeroDivisionError. The fix is a guard (empty cart → average 0.0), not a
change to the totals.
"""

from __future__ import annotations

from typing import Any, Dict, List


def line_total(price: float, qty: int) -> float:
    if qty < 0:
        raise ValueError("qty must be >= 0")
    return round(price * qty, 2)


def subtotal(items: List[Dict[str, Any]]) -> float:
    return round(
        sum(line_total(float(item["price"]), int(item["qty"])) for item in items),
        2,
    )


def bulk_discount(items: List[Dict[str, Any]]) -> float:
    """5% off when 3+ bulk lines (qty >= 10) are present."""
    bulk_lines = sum(1 for item in items if int(item["qty"]) >= 10)
    if bulk_lines >= 3:
        return round(subtotal(items) * 0.05, 2)
    return 0.0


def summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = round(subtotal(items) - bulk_discount(items), 2)
    average = round(total / len(items), 2)  # BUG: empty cart -> ZeroDivisionError
    return {
        "lines": len(items),
        "subtotal": subtotal(items),
        "discount": bulk_discount(items),
        "total": total,
        "average_item_price": average,
    }
