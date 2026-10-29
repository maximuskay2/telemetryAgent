"""Proof-shop suite: ~20 tests, all green on the buggy original.

None covers the empty cart — that is the bug TelemetryAgent finds, proves
with its own repro test, and fixes.
"""

import pytest
from fastapi.testclient import TestClient

from app.cart import bulk_discount, line_total, subtotal, summary
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_line_total_basic():
    assert line_total(2.5, 4) == 10.0


def test_line_total_rounds():
    assert line_total(0.1, 3) == 0.3


def test_line_total_zero_qty():
    assert line_total(9.99, 0) == 0.0


def test_line_total_negative_qty_rejected():
    with pytest.raises(ValueError):
        line_total(1.0, -1)


def test_subtotal_sums_lines():
    items = [
        {"name": "a", "price": 2.0, "qty": 3},
        {"name": "b", "price": 1.5, "qty": 2},
    ]
    assert subtotal(items) == 9.0


def test_subtotal_ignores_zero_qty():
    items = [{"name": "a", "price": 5.0, "qty": 0}]
    assert subtotal(items) == 0.0


def test_bulk_discount_needs_three_bulk_lines():
    items = [
        {"name": f"n{i}", "price": 10.0, "qty": 10} for i in range(2)
    ]
    assert bulk_discount(items) == 0.0


def test_bulk_discount_applies():
    items = [
        {"name": f"n{i}", "price": 10.0, "qty": 10} for i in range(3)
    ]
    assert bulk_discount(items) == 15.0


def test_bulk_discount_ignores_small_lines():
    items = [{"name": f"n{i}", "price": 10.0, "qty": 1} for i in range(5)]
    assert bulk_discount(items) == 0.0


def test_summary_totals():
    items = [{"name": "a", "price": 4.0, "qty": 2}]
    result = summary(items)
    assert result["lines"] == 1
    assert result["subtotal"] == 8.0
    assert result["discount"] == 0.0
    assert result["total"] == 8.0
    assert result["average_item_price"] == 8.0


def test_summary_with_discount():
    items = [
        {"name": f"n{i}", "price": 10.0, "qty": 10} for i in range(3)
    ]
    result = summary(items)
    assert result["total"] == 285.0
    assert result["average_item_price"] == 95.0


def test_summary_average_over_lines():
    items = [
        {"name": "a", "price": 3.0, "qty": 1},
        {"name": "b", "price": 5.0, "qty": 1},
    ]
    assert summary(items)["average_item_price"] == 4.0


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_checkout_ok():
    response = client.post(
        "/checkout", json={"items": [{"name": "a", "price": 2.0, "qty": 2}]}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 4.0


def test_checkout_validates_price():
    response = client.post(
        "/checkout", json={"items": [{"name": "a", "price": -1, "qty": 1}]}
    )
    assert response.status_code == 422


def test_checkout_validates_name():
    response = client.post(
        "/checkout", json={"items": [{"name": "", "price": 1, "qty": 1}]}
    )
    assert response.status_code == 422


def test_checkout_bulk_order():
    response = client.post(
        "/checkout",
        json={
            "items": [
                {"name": f"n{i}", "price": 10.0, "qty": 10}
                for i in range(3)
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["discount"] == 15.0


def test_checkout_single_bulk_line_no_discount():
    response = client.post(
        "/checkout",
        json={"items": [{"name": "a", "price": 1.0, "qty": 25}]},
    )
    assert response.status_code == 200
    assert response.json()["discount"] == 0.0


def test_checkout_zero_qty_line():
    response = client.post(
        "/checkout",
        json={"items": [{"name": "a", "price": 3.0, "qty": 0}]},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0.0


def test_checkout_missing_items_defaults_empty_list_shape():
    # Missing body key still validates (defaults to []); the endpoint
    # would crash, so only the validation layer is asserted here.
    from app.main import CheckoutIn

    assert CheckoutIn().items == []
