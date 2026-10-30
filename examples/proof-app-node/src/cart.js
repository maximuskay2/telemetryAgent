// Cart pricing for the proof shop.
//
// BUG (for TelemetryAgent to find): `summary()` reads `items[0].currency`,
// so checking out an EMPTY cart throws
// `TypeError: Cannot read properties of undefined (reading 'currency')`.
// The fix is a guard (empty cart -> currency "USD", average 0.0), not a
// change to the totals.

export function round2(n) {
  return Math.round(n * 100) / 100;
}

export function lineTotal(price, qty) {
  if (qty < 0) {
    throw new RangeError("qty must be >= 0");
  }
  return round2(price * qty);
}

export function subtotal(items) {
  return round2(
    items.reduce((acc, it) => acc + lineTotal(it.price, it.qty), 0),
  );
}

export function bulkDiscount(items) {
  // 5% off when 3+ bulk lines (qty >= 10) are present.
  const bulkLines = items.filter((it) => it.qty >= 10).length;
  if (bulkLines >= 3) {
    return round2(subtotal(items) * 0.05);
  }
  return 0;
}

export function summary(items) {
  const total = round2(subtotal(items) - bulkDiscount(items));
  const average = round2(total / items.length);
  // BUG: empty cart -> TypeError (items[0] is undefined; JS has no
  // integer-division crash, so the missing empty-cart guard bites here).
  const currency = items[0].currency ?? "USD";
  return {
    lines: items.length,
    subtotal: subtotal(items),
    discount: bulkDiscount(items),
    total,
    average_item_price: average,
    currency,
  };
}
