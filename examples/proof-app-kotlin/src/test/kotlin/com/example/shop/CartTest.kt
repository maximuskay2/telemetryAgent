package com.example.shop

import com.example.shop.Cart.Item
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test

/**
 * Proof-shop unit suite: green on the buggy original. Nothing covers the
 * empty cart — that is the bug TelemetryAgent finds, proves with its own
 * repro test, and fixes. Money is integer cents.
 */
class CartTest {

    private fun item(name: String, priceCents: Long, qty: Int) = Item(name, priceCents, qty)

    @Test
    fun `line total basic`() {
        assertEquals(1000, Cart.lineTotal(250, 4))
    }

    @Test
    fun `line total small`() {
        assertEquals(30, Cart.lineTotal(10, 3))
    }

    @Test
    fun `line total zero qty`() {
        assertEquals(0, Cart.lineTotal(999, 0))
    }

    @Test
    fun `line total negative qty rejected`() {
        assertThrows(IllegalArgumentException::class.java) { Cart.lineTotal(100, -1) }
    }

    @Test
    fun `subtotal sums lines`() {
        assertEquals(900, Cart.subtotal(listOf(item("a", 200, 3), item("b", 150, 2))))
    }

    @Test
    fun `subtotal ignores zero qty`() {
        assertEquals(0, Cart.subtotal(listOf(item("a", 500, 0))))
    }

    @Test
    fun `bulk discount needs three bulk lines`() {
        assertEquals(0, Cart.bulkDiscount(listOf(item("n0", 1000, 10), item("n1", 1000, 10))))
    }

    @Test
    fun `bulk discount applies`() {
        val items = listOf(item("n0", 1000, 10), item("n1", 1000, 10), item("n2", 1000, 10))
        assertEquals(1500, Cart.bulkDiscount(items))
    }

    @Test
    fun `bulk discount ignores small lines`() {
        val items = (0..4).map { item("n$it", 1000, 1) }
        assertEquals(0, Cart.bulkDiscount(items))
    }

    @Test
    fun `summary totals`() {
        val result = Cart.summary(listOf(item("a", 400, 2)))
        assertEquals(1, result.lines)
        assertEquals(800, result.subtotalCents)
        assertEquals(0, result.discountCents)
        assertEquals(800, result.totalCents)
        assertEquals(800, result.averageCents)
        assertEquals("USD", result.currency)
    }

    @Test
    fun `summary with discount`() {
        val items = listOf(item("n0", 1000, 10), item("n1", 1000, 10), item("n2", 1000, 10))
        val result = Cart.summary(items)
        assertEquals(28500, result.totalCents)
        assertEquals(9500, result.averageCents)
    }

    @Test
    fun `summary average over lines`() {
        val items = listOf(item("a", 300, 1), item("b", 500, 1))
        assertEquals(400, Cart.summary(items).averageCents)
    }
}
