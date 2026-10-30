// Average item price.
// BUG: an empty list returns NaN instead of throwing.
function average(nums) {
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function totalWithTax(nums, rate) {
  return average(nums) * (1 + rate);
}

module.exports = { average, totalWithTax };
