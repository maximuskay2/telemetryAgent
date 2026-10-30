package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

/** Proof-shop unit suite: green on the buggy original. Nothing covers the
 * empty cart — that is the bug TelemetryAgent finds, proves with its own
 * repro test, and fixes. Money is integer cents. */
class CartTest {

    private static Cart.Item item(String name, long priceCents, int qty) {
        return new Cart.Item(name, priceCents, qty);
    }

    @Test
    void lineTotalBasic() {
        assertEquals(1000, Cart.lineTotal(250, 4));
    }

    @Test
    void lineTotalSmall() {
        assertEquals(30, Cart.lineTotal(10, 3));
    }

    @Test
    void lineTotalZeroQty() {
        assertEquals(0, Cart.lineTotal(999, 0));
    }

    @Test
    void lineTotalNegativeQtyRejected() {
        assertThrows(IllegalArgumentException.class, () -> Cart.lineTotal(100, -1));
    }

    @Test
    void subtotalSumsLines() {
        List<Cart.Item> items = List.of(item("a", 200, 3), item("b", 150, 2));
        assertEquals(900, Cart.subtotal(items));
    }

    @Test
    void subtotalIgnoresZeroQty() {
        assertEquals(0, Cart.subtotal(List.of(item("a", 500, 0))));
    }

    @Test
    void bulkDiscountNeedsThreeBulkLines() {
        List<Cart.Item> items = List.of(item("n0", 1000, 10), item("n1", 1000, 10));
        assertEquals(0, Cart.bulkDiscount(items));
    }

    @Test
    void bulkDiscountApplies() {
        List<Cart.Item> items =
                List.of(item("n0", 1000, 10), item("n1", 1000, 10), item("n2", 1000, 10));
        assertEquals(1500, Cart.bulkDiscount(items));
    }

    @Test
    void bulkDiscountIgnoresSmallLines() {
        List<Cart.Item> items =
                List.of(
                        item("n0", 1000, 1),
                        item("n1", 1000, 1),
                        item("n2", 1000, 1),
                        item("n3", 1000, 1),
                        item("n4", 1000, 1));
        assertEquals(0, Cart.bulkDiscount(items));
    }

    @Test
    void summaryTotals() {
        Cart.Summary result = Cart.summary(List.of(item("a", 400, 2)));
        assertEquals(1, result.lines());
        assertEquals(800, result.subtotalCents());
        assertEquals(0, result.discountCents());
        assertEquals(800, result.totalCents());
        assertEquals(800, result.averageCents());
        assertEquals("USD", result.currency());
    }

    @Test
    void summaryWithDiscount() {
        List<Cart.Item> items =
                List.of(item("n0", 1000, 10), item("n1", 1000, 10), item("n2", 1000, 10));
        Cart.Summary result = Cart.summary(items);
        assertEquals(28500, result.totalCents());
        assertEquals(9500, result.averageCents());
    }

    @Test
    void summaryAverageOverLines() {
        List<Cart.Item> items = List.of(item("a", 300, 1), item("b", 500, 1));
        assertEquals(400, Cart.summary(items).averageCents());
    }
}
