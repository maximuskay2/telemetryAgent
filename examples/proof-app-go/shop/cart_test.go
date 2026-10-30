package shop

// Proof-shop unit suite: green on the buggy original. Nothing covers the
// empty cart — that is the bug TelemetryAgent finds, proves with its own
// repro test, and fixes. Money is integer cents.

import "testing"

func item(name string, priceCents int64, qty int) Item {
	return Item{Name: name, PriceCents: priceCents, Qty: qty, Currency: "USD"}
}

func TestLineTotalBasic(t *testing.T) {
	got, err := LineTotal(250, 4)
	if err != nil || got != 1000 {
		t.Fatalf("got %d, %v; want 1000, nil", got, err)
	}
}

func TestLineTotalSmall(t *testing.T) {
	got, err := LineTotal(10, 3)
	if err != nil || got != 30 {
		t.Fatalf("got %d, %v; want 30, nil", got, err)
	}
}

func TestLineTotalZeroQty(t *testing.T) {
	got, err := LineTotal(999, 0)
	if err != nil || got != 0 {
		t.Fatalf("got %d, %v; want 0, nil", got, err)
	}
}

func TestLineTotalNegativeQtyRejected(t *testing.T) {
	if _, err := LineTotal(100, -1); err == nil {
		t.Fatal("want error for negative qty")
	}
}

func TestSubtotalSumsLines(t *testing.T) {
	items := []Item{item("a", 200, 3), item("b", 150, 2)}
	if got := Subtotal(items); got != 900 {
		t.Fatalf("got %d; want 900", got)
	}
}

func TestSubtotalIgnoresZeroQty(t *testing.T) {
	if got := Subtotal([]Item{item("a", 500, 0)}); got != 0 {
		t.Fatalf("got %d; want 0", got)
	}
}

func TestBulkDiscountNeedsThreeBulkLines(t *testing.T) {
	items := []Item{item("n0", 1000, 10), item("n1", 1000, 10)}
	if got := BulkDiscount(items); got != 0 {
		t.Fatalf("got %d; want 0", got)
	}
}

func TestBulkDiscountApplies(t *testing.T) {
	items := []Item{item("n0", 1000, 10), item("n1", 1000, 10), item("n2", 1000, 10)}
	if got := BulkDiscount(items); got != 1500 {
		t.Fatalf("got %d; want 1500", got)
	}
}

func TestBulkDiscountIgnoresSmallLines(t *testing.T) {
	items := []Item{
		item("n0", 1000, 1), item("n1", 1000, 1), item("n2", 1000, 1),
		item("n3", 1000, 1), item("n4", 1000, 1),
	}
	if got := BulkDiscount(items); got != 0 {
		t.Fatalf("got %d; want 0", got)
	}
}

func TestSummaryTotals(t *testing.T) {
	got := Summarize([]Item{item("a", 400, 2)})
	if got.Lines != 1 || got.Subtotal != 8 || got.Discount != 0 || got.Total != 8 ||
		got.AveragePrice != 8 || got.Currency != "USD" {
		t.Fatalf("unexpected summary: %+v", got)
	}
}

func TestSummaryWithDiscount(t *testing.T) {
	items := []Item{item("n0", 1000, 10), item("n1", 1000, 10), item("n2", 1000, 10)}
	got := Summarize(items)
	if got.Total != 285 || got.AveragePrice != 95 {
		t.Fatalf("unexpected summary: %+v", got)
	}
}

func TestSummaryAverageOverLines(t *testing.T) {
	items := []Item{item("a", 300, 1), item("b", 500, 1)}
	if got := Summarize(items); got.AveragePrice != 4 {
		t.Fatalf("got %v; want 4", got.AveragePrice)
	}
}

func TestSummaryKeepsItemCurrency(t *testing.T) {
	got := Summarize([]Item{{Name: "a", PriceCents: 400, Qty: 2, Currency: "EUR"}})
	if got.Currency != "EUR" {
		t.Fatalf("got %q; want EUR", got.Currency)
	}
}
