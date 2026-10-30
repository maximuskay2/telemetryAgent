<?php

declare(strict_types=1);

namespace ProofShop\Tests;

use PHPUnit\Framework\TestCase;
use ProofShop\Cart;
use ProofShop\Shop;

/**
 * Proof-shop suite: green on the buggy original. Nothing covers the
 * empty cart — that is the bug TelemetryAgent finds, proves with its own
 * repro test, and fixes. Unit tests use integer cents; API tests go
 * through Shop::handle with dollars on the wire.
 */
final class ShopTest extends TestCase
{
    /** @return array<string, mixed> */
    private static function item(string $name, int $priceCents, int $qty): array
    {
        return ['name' => $name, 'price_cents' => $priceCents, 'qty' => $qty, 'currency' => 'USD'];
    }

    public function testLineTotalBasic(): void
    {
        $this->assertSame(1000, Cart::lineTotal(250, 4));
    }

    public function testLineTotalSmall(): void
    {
        $this->assertSame(30, Cart::lineTotal(10, 3));
    }

    public function testLineTotalZeroQty(): void
    {
        $this->assertSame(0, Cart::lineTotal(999, 0));
    }

    public function testLineTotalNegativeQtyRejected(): void
    {
        $this->expectException(\InvalidArgumentException::class);
        Cart::lineTotal(100, -1);
    }

    public function testSubtotalSumsLines(): void
    {
        $items = [self::item('a', 200, 3), self::item('b', 150, 2)];
        $this->assertSame(900, Cart::subtotal($items));
    }

    public function testSubtotalIgnoresZeroQty(): void
    {
        $this->assertSame(0, Cart::subtotal([self::item('a', 500, 0)]));
    }

    public function testBulkDiscountNeedsThreeBulkLines(): void
    {
        $items = [self::item('n0', 1000, 10), self::item('n1', 1000, 10)];
        $this->assertSame(0, Cart::bulkDiscount($items));
    }

    public function testBulkDiscountApplies(): void
    {
        $items = [self::item('n0', 1000, 10), self::item('n1', 1000, 10), self::item('n2', 1000, 10)];
        $this->assertSame(1500, Cart::bulkDiscount($items));
    }

    public function testBulkDiscountIgnoresSmallLines(): void
    {
        $items = [
            self::item('n0', 1000, 1), self::item('n1', 1000, 1), self::item('n2', 1000, 1),
            self::item('n3', 1000, 1), self::item('n4', 1000, 1),
        ];
        $this->assertSame(0, Cart::bulkDiscount($items));
    }

    public function testSummaryTotals(): void
    {
        $result = Cart::summary([self::item('a', 400, 2)]);
        $this->assertSame(1, $result['lines']);
        $this->assertSame(8.0, $result['subtotal']);
        $this->assertSame(0.0, $result['discount']);
        $this->assertSame(8.0, $result['total']);
        $this->assertSame(8.0, $result['average_item_price']);
        $this->assertSame('USD', $result['currency']);
    }

    public function testSummaryWithDiscount(): void
    {
        $items = [self::item('n0', 1000, 10), self::item('n1', 1000, 10), self::item('n2', 1000, 10)];
        $result = Cart::summary($items);
        $this->assertSame(285.0, $result['total']);
        $this->assertSame(95.0, $result['average_item_price']);
    }

    public function testSummaryAverageOverLines(): void
    {
        $items = [self::item('a', 300, 1), self::item('b', 500, 1)];
        $this->assertSame(4.0, Cart::summary($items)['average_item_price']);
    }

    public function testHealth(): void
    {
        [$code, $data] = Shop::handle('GET', '/health', '');
        $this->assertSame(200, $code);
        $this->assertSame(['status' => 'ok'], $data);
    }

    public function testCheckoutOk(): void
    {
        [$code, $data] = Shop::handle('POST', '/checkout', '{"items": [{"name": "a", "price": 2.0, "qty": 2}]}');
        $this->assertSame(200, $code);
        $this->assertSame(4.0, $data['total']);
    }

    public function testCheckoutValidatesPrice(): void
    {
        [$code,] = Shop::handle('POST', '/checkout', '{"items": [{"name": "a", "price": -1, "qty": 1}]}');
        $this->assertSame(422, $code);
    }

    public function testCheckoutValidatesName(): void
    {
        [$code,] = Shop::handle('POST', '/checkout', '{"items": [{"name": "", "price": 1, "qty": 1}]}');
        $this->assertSame(422, $code);
    }

    public function testCheckoutBulkOrder(): void
    {
        $body = '{"items": [{"name": "n0", "price": 10.0, "qty": 10},'
            .' {"name": "n1", "price": 10.0, "qty": 10},'
            .' {"name": "n2", "price": 10.0, "qty": 10}]}';
        [$code, $data] = Shop::handle('POST', '/checkout', $body);
        $this->assertSame(200, $code);
        $this->assertSame(15.0, $data['discount']);
    }

    public function testCheckoutSingleBulkLineHasNoDiscount(): void
    {
        [$code, $data] = Shop::handle('POST', '/checkout', '{"items": [{"name": "a", "price": 1.0, "qty": 25}]}');
        $this->assertSame(200, $code);
        $this->assertSame(0.0, $data['discount']);
    }

    public function testCheckoutZeroQtyLine(): void
    {
        [$code, $data] = Shop::handle('POST', '/checkout', '{"items": [{"name": "a", "price": 3.0, "qty": 0}]}');
        $this->assertSame(200, $code);
        $this->assertSame(0.0, $data['total']);
    }

    public function testUnknownRouteIs404(): void
    {
        [$code,] = Shop::handle('GET', '/nope', '');
        $this->assertSame(404, $code);
    }
}
