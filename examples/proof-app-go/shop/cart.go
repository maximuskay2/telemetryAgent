// Package shop is a tiny cart service. Money is integer cents internally;
// the HTTP layer converts to/from dollars so the wire shape matches the
// Python proof app.
package shop

import "errors"

// Item is one validated cart line.
type Item struct {
	Name       string
	PriceCents int64
	Qty        int
	Currency   string
}

// Summary is the checkout receipt.
type Summary struct {
	Lines        int    `json:"lines"`
	Subtotal     float64 `json:"subtotal"`
	Discount     float64 `json:"discount"`
	Total        float64 `json:"total"`
	AveragePrice float64 `json:"average_item_price"`
	Currency     string  `json:"currency"`
}

func centsToDollars(cents int64) float64 {
	return float64(cents) / 100
}

// LineTotal prices one line.
func LineTotal(priceCents int64, qty int) (int64, error) {
	if qty < 0 {
		return 0, errors.New("qty must be >= 0")
	}
	return priceCents * int64(qty), nil
}

// Subtotal sums the lines.
func Subtotal(items []Item) int64 {
	var sum int64
	for _, item := range items {
		line, _ := LineTotal(item.PriceCents, item.Qty)
		sum += line
	}
	return sum
}

// BulkDiscount is 5% off when 3+ bulk lines (qty >= 10) are present.
func BulkDiscount(items []Item) int64 {
	bulkLines := 0
	for _, item := range items {
		if item.Qty >= 10 {
			bulkLines++
		}
	}
	if bulkLines >= 3 {
		return (Subtotal(items)*5 + 50) / 100
	}
	return 0
}

// Summary totals the cart.
//
// BUG (for TelemetryAgent to find): Summary divides by len(items) when
// computing the average item price, so checking out an EMPTY cart panics
// with integer divide by zero. The fix is a guard (empty cart → average
// 0), not a change to the totals.
func Summarize(items []Item) Summary {
	total := Subtotal(items) - BulkDiscount(items)
	average := total / int64(len(items)) // BUG: empty cart -> panic
	currency := "USD"
	if len(items) > 0 {
		currency = items[0].Currency
	}
	return Summary{
		Lines:        len(items),
		Subtotal:     centsToDollars(Subtotal(items)),
		Discount:     centsToDollars(BulkDiscount(items)),
		Total:        centsToDollars(total),
		AveragePrice: centsToDollars(average),
		Currency:     currency,
	}
}
