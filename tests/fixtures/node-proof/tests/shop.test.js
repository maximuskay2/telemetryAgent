const { describe, it } = require('node:test');
const assert = require('node:assert');
const { average, totalWithTax } = require('../src/shop');

describe('average', () => {
  it('averages a list', () => {
    assert.strictEqual(average([2, 4]), 3);
  });

  it('handles one item', () => {
    assert.strictEqual(average([5]), 5);
  });

  it('adds tax', () => {
    assert.strictEqual(totalWithTax([10, 20], 0.5), 22.5);
  });
});
