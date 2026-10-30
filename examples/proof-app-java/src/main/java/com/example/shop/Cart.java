package com.example.shop;

import java.util.List;

/**
 * Cart pricing for the proof shop. Money is integer cents internally; the
 * HTTP layer converts to/from dollars so the wire shape matches the Python
 * proof app.
 *
 * <p>BUG (for TelemetryAgent to find): {@code summary()} divides by {@code
 * items.size()} when computing the average item price, so checking out an
 * EMPTY cart raises {@code ArithmeticException: / by zero}. The fix is a
 * guard (empty cart → average 0), not a change to the totals.
 */
public final class Cart {
    private Cart() {}

    public record Item(String name, long priceCents, int qty, String currency) {
        public Item(String name, long priceCents, int qty) {
            this(name, priceCents, qty, "USD");
        }
    }

    public record Summary(
            int lines,
            long subtotalCents,
            long discountCents,
            long totalCents,
            long averageCents,
            String currency) {}

    public static long lineTotal(long priceCents, int qty) {
        if (qty < 0) {
            throw new IllegalArgumentException("qty must be >= 0");
        }
        return priceCents * qty;
    }

    public static long subtotal(List<Item> items) {
        long sum = 0;
        for (Item item : items) {
            sum += lineTotal(item.priceCents(), item.qty());
        }
        return sum;
    }

    /** 5% off when 3+ bulk lines (qty >= 10) are present. */
    public static long bulkDiscount(List<Item> items) {
        long bulkLines = items.stream().filter(item -> item.qty() >= 10).count();
        if (bulkLines >= 3) {
            return (subtotal(items) * 5 + 50) / 100;
        }
        return 0;
    }

    public static Summary summary(List<Item> items) {
        long total = subtotal(items) - bulkDiscount(items);
        long average = total / items.size(); // BUG: empty cart -> ArithmeticException
        String currency = items.isEmpty() ? "USD" : items.get(0).currency();
        return new Summary(
                items.size(), subtotal(items), bulkDiscount(items), total, average, currency);
    }
}
