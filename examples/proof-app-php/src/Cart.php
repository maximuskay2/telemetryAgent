<?php

declare(strict_types=1);

namespace ProofShop;

/**
 * Cart pricing for the proof shop. Money is integer cents internally; the
 * HTTP layer converts to/from dollars so the wire shape matches the Python
 * proof app.
 *
 * BUG (for TelemetryAgent to find): summary() divides by count($items)
 * when computing the average item price, so checking out an EMPTY cart
 * raises DivisionByZeroError. The fix is a guard (empty cart → average
 * 0), not a change to the totals.
 *
 * Items are assoc arrays: ['name' => string, 'price_cents' => int,
 * 'qty' => int, 'currency' => string].
 */
final class Cart
{
    public static function lineTotal(int $priceCents, int $qty): int
    {
        if ($qty < 0) {
            throw new \InvalidArgumentException('qty must be >= 0');
        }

        return $priceCents * $qty;
    }

    /** @param array<int, array<string, mixed>> $items */
    public static function subtotal(array $items): int
    {
        $sum = 0;
        foreach ($items as $item) {
            $sum += self::lineTotal($item['price_cents'], $item['qty']);
        }

        return $sum;
    }

    /** 5% off when 3+ bulk lines (qty >= 10) are present. */
    public static function bulkDiscount(array $items): int
    {
        $bulkLines = 0;
        foreach ($items as $item) {
            if ($item['qty'] >= 10) {
                $bulkLines++;
            }
        }
        if ($bulkLines >= 3) {
            return intdiv(self::subtotal($items) * 5 + 50, 100);
        }

        return 0;
    }

    /** @param array<int, array<string, mixed>> $items */
    public static function summary(array $items): array
    {
        $total = self::subtotal($items) - self::bulkDiscount($items);
        $average = intdiv($total, count($items)); // BUG: empty cart -> DivisionByZeroError
        $currency = count($items) === 0 ? 'USD' : $items[0]['currency'];

        return [
            'lines' => count($items),
            'subtotal' => self::subtotal($items) / 100.0,
            'discount' => self::bulkDiscount($items) / 100.0,
            'total' => $total / 100.0,
            'average_item_price' => $average / 100.0,
            'currency' => $currency,
        ];
    }
}
