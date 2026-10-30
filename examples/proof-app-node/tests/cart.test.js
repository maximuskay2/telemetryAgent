// Proof-shop unit suite: green on the buggy original. Nothing covers the
// empty cart — that is the bug TelemetryAgent finds, proves with its own
// repro test, and fixes.
import test from "node:test";
import assert from "node:assert/strict";
import {
  bulkDiscount,
  lineTotal,
  subtotal,
  summary,
} from "../src/cart.js";

test("line_total basic", () => {
  assert.equal(lineTotal(2.5, 4), 10.0);
});

test("line_total rounds", () => {
  assert.equal(lineTotal(0.1, 3), 0.3);
});

test("line_total zero qty", () => {
  assert.equal(lineTotal(9.99, 0), 0.0);
});

test("line_total negative qty rejected", () => {
  assert.throws(() => lineTotal(1.0, -1), RangeError);
});

test("subtotal sums lines", () => {
  const items = [
    { name: "a", price: 2.0, qty: 3 },
    { name: "b", price: 1.5, qty: 2 },
  ];
  assert.equal(subtotal(items), 9.0);
});

test("subtotal ignores zero qty", () => {
  assert.equal(subtotal([{ name: "a", price: 5.0, qty: 0 }]), 0.0);
});

test("bulk discount needs three bulk lines", () => {
  const items = [0, 1].map((i) => ({ name: `n${i}`, price: 10.0, qty: 10 }));
  assert.equal(bulkDiscount(items), 0.0);
});

test("bulk discount applies", () => {
  const items = [0, 1, 2].map((i) => ({
    name: `n${i}`,
    price: 10.0,
    qty: 10,
  }));
  assert.equal(bulkDiscount(items), 15.0);
});

test("bulk discount ignores small lines", () => {
  const items = [0, 1, 2, 3, 4].map((i) => ({
    name: `n${i}`,
    price: 10.0,
    qty: 1,
  }));
  assert.equal(bulkDiscount(items), 0.0);
});

test("summary totals", () => {
  const result = summary([{ name: "a", price: 4.0, qty: 2 }]);
  assert.equal(result.lines, 1);
  assert.equal(result.subtotal, 8.0);
  assert.equal(result.discount, 0.0);
  assert.equal(result.total, 8.0);
  assert.equal(result.average_item_price, 8.0);
  assert.equal(result.currency, "USD");
});

test("summary with discount", () => {
  const items = [0, 1, 2].map((i) => ({
    name: `n${i}`,
    price: 10.0,
    qty: 10,
  }));
  const result = summary(items);
  assert.equal(result.total, 285.0);
  assert.equal(result.average_item_price, 95.0);
});

test("summary average over lines", () => {
  const items = [
    { name: "a", price: 3.0, qty: 1 },
    { name: "b", price: 5.0, qty: 1 },
  ];
  assert.equal(summary(items).average_item_price, 4.0);
});

test("summary keeps item currency", () => {
  const items = [{ name: "a", price: 4.0, qty: 2, currency: "EUR" }];
  assert.equal(summary(items).currency, "EUR");
});
