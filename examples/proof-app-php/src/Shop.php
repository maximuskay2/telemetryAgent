<?php

declare(strict_types=1);

namespace ProofShop;

/**
 * Proof shop HTTP handling as a pure function (method + path + body in,
 * [status, data] out) so the suite needs no sockets. public/index.php is
 * the thin built-in-server wrapper.
 */
final class Shop
{
    /** @return array{0: int, 1: array<string, mixed>} */
    public static function handle(string $method, string $path, string $body): array
    {
        if ($method === 'GET' && $path === '/health') {
            return [200, ['status' => 'ok']];
        }
        if ($method === 'POST' && $path === '/checkout') {
            $items = self::parseItems($body);
            if ($items === null) {
                return [422, ['detail' => 'invalid items']];
            }
            // No try/catch on purpose: the empty-cart DivisionByZeroError
            // must crash with a full stack trace so the forwarder ships it
            // to TelemetryAgent.
            return [200, Cart::summary($items)];
        }

        return [404, ['detail' => 'not found']];
    }

    /** Returns null when the body fails validation (→ 422). */
    public static function parseItems(string $body): ?array
    {
        try {
            $root = json_decode($body === '' ? '{}' : $body, true, 512, JSON_THROW_ON_ERROR);
        } catch (\JsonException) {
            return null;
        }
        if (!is_array($root)) {
            return null;
        }
        $rawItems = $root['items'] ?? [];
        if (!is_array($rawItems) || ($rawItems !== [] && array_is_list($rawItems) === false)) {
            return null;
        }
        $items = [];
        foreach ($rawItems as $raw) {
            if (!is_array($raw)) {
                return null;
            }
            $name = $raw['name'] ?? null;
            if (!is_string($name) || $name === '') {
                return null;
            }
            $price = $raw['price'] ?? null;
            if ((!is_int($price) && !is_float($price)) || $price < 0) {
                return null;
            }
            $qty = $raw['qty'] ?? null;
            if (!is_int($qty) && !(is_float($qty) && floor($qty) === $qty)) {
                return null;
            }
            if ($qty < 0) {
                return null;
            }
            $currency = $raw['currency'] ?? 'USD';
            if (!is_string($currency)) {
                return null;
            }
            $items[] = [
                'name' => $name,
                'price_cents' => (int) round($price * 100),
                'qty' => (int) $qty,
                'currency' => $currency,
            ];
        }

        return $items;
    }
}
