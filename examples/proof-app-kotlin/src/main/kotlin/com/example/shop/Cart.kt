package com.example.shop

/**
 * Cart pricing for the proof shop. Money is integer cents internally; the
 * HTTP layer converts to/from dollars so the wire shape matches the Python
 * proof app.
 *
 * BUG (for TelemetryAgent to find): `summary()` divides by `items.size`
 * when computing the average item price, so checking out an EMPTY cart
 * raises `ArithmeticException: / by zero`. The fix is a guard (empty cart
 * → average 0), not a change to the totals.
 */
object Cart {
    data class Item(
        val name: String,
        val priceCents: Long,
        val qty: Int,
        val currency: String = "USD",
    )

    data class Summary(
        val lines: Int,
        val subtotalCents: Long,
        val discountCents: Long,
        val totalCents: Long,
        val averageCents: Long,
        val currency: String,
    )

    fun lineTotal(priceCents: Long, qty: Int): Long {
        require(qty >= 0) { "qty must be >= 0" }
        return priceCents * qty
    }

    fun subtotal(items: List<Item>): Long = items.sumOf { lineTotal(it.priceCents, it.qty) }

    /** 5% off when 3+ bulk lines (qty >= 10) are present. */
    fun bulkDiscount(items: List<Item>): Long {
        val bulkLines = items.count { it.qty >= 10 }
        if (bulkLines >= 3) {
            return (subtotal(items) * 5 + 50) / 100
        }
        return 0
    }

    fun summary(items: List<Item>): Summary {
        val total = subtotal(items) - bulkDiscount(items)
        val average = total / items.size // BUG: empty cart -> ArithmeticException
        val currency = if (items.isEmpty()) "USD" else items[0].currency
        return Summary(
            lines = items.size,
            subtotalCents = subtotal(items),
            discountCents = bulkDiscount(items),
            totalCents = total,
            averageCents = average,
            currency = currency,
        )
    }
}
