//! Cart pricing for the proof shop. Money is integer cents internally; the
//! HTTP layer converts to/from dollars so the wire shape matches the Python
//! proof app.
//!
//! BUG (for TelemetryAgent to find): [`summary`] divides by `items.len()`
//! when computing the average item price, so checking out an EMPTY cart
//! panics with `attempt to divide by zero`. The fix is a guard (empty cart
//! → average 0), not a change to the totals.

/// One validated cart line.
#[derive(Debug, Clone, PartialEq)]
pub struct Item {
    pub name: String,
    pub price_cents: i64,
    pub qty: i64,
    pub currency: String,
}

impl Item {
    pub fn new(name: &str, price_cents: i64, qty: i64) -> Item {
        Item {
            name: name.to_string(),
            price_cents,
            qty,
            currency: "USD".to_string(),
        }
    }
}

/// The checkout receipt (cents; the server renders dollars).
#[derive(Debug, Clone, PartialEq)]
pub struct Summary {
    pub lines: usize,
    pub subtotal_cents: i64,
    pub discount_cents: i64,
    pub total_cents: i64,
    pub average_cents: i64,
    pub currency: String,
}

/// Price one line.
pub fn line_total(price_cents: i64, qty: i64) -> Result<i64, String> {
    if qty < 0 {
        return Err("qty must be >= 0".to_string());
    }
    Ok(price_cents * qty)
}

/// Sum the lines.
pub fn subtotal(items: &[Item]) -> i64 {
    items
        .iter()
        .map(|item| line_total(item.price_cents, item.qty).unwrap_or(0))
        .sum()
}

/// 5% off when 3+ bulk lines (qty >= 10) are present.
pub fn bulk_discount(items: &[Item]) -> i64 {
    let bulk_lines = items.iter().filter(|item| item.qty >= 10).count();
    if bulk_lines >= 3 {
        (subtotal(items) * 5 + 50) / 100
    } else {
        0
    }
}

/// Total the cart.
pub fn summary(items: &[Item]) -> Summary {
    let total = subtotal(items) - bulk_discount(items);
    let average = total / items.len() as i64; // BUG: empty cart -> attempt to divide by zero
    let currency = items
        .first()
        .map(|item| item.currency.clone())
        .unwrap_or_else(|| "USD".to_string());
    Summary {
        lines: items.len(),
        subtotal_cents: subtotal(items),
        discount_cents: bulk_discount(items),
        total_cents: total,
        average_cents: average,
        currency,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Proof-shop unit suite: green on the buggy original. Nothing covers
    /// the empty cart — that is the bug TelemetryAgent finds, proves with
    /// its own repro test, and fixes. Money is integer cents.

    #[test]
    fn line_total_basic() {
        assert_eq!(line_total(250, 4), Ok(1000));
    }

    #[test]
    fn line_total_small() {
        assert_eq!(line_total(10, 3), Ok(30));
    }

    #[test]
    fn line_total_zero_qty() {
        assert_eq!(line_total(999, 0), Ok(0));
    }

    #[test]
    fn line_total_negative_qty_rejected() {
        assert!(line_total(100, -1).is_err());
    }

    #[test]
    fn subtotal_sums_lines() {
        let items = vec![Item::new("a", 200, 3), Item::new("b", 150, 2)];
        assert_eq!(subtotal(&items), 900);
    }

    #[test]
    fn subtotal_ignores_zero_qty() {
        assert_eq!(subtotal(&[Item::new("a", 500, 0)]), 0);
    }

    #[test]
    fn bulk_discount_needs_three_bulk_lines() {
        let items = vec![Item::new("n0", 1000, 10), Item::new("n1", 1000, 10)];
        assert_eq!(bulk_discount(&items), 0);
    }

    #[test]
    fn bulk_discount_applies() {
        let items = vec![
            Item::new("n0", 1000, 10),
            Item::new("n1", 1000, 10),
            Item::new("n2", 1000, 10),
        ];
        assert_eq!(bulk_discount(&items), 1500);
    }

    #[test]
    fn bulk_discount_ignores_small_lines() {
        let items: Vec<Item> = (0..5).map(|i| Item::new(&format!("n{i}"), 1000, 1)).collect();
        assert_eq!(bulk_discount(&items), 0);
    }

    #[test]
    fn summary_totals() {
        let result = summary(&[Item::new("a", 400, 2)]);
        assert_eq!(result.lines, 1);
        assert_eq!(result.subtotal_cents, 800);
        assert_eq!(result.discount_cents, 0);
        assert_eq!(result.total_cents, 800);
        assert_eq!(result.average_cents, 800);
        assert_eq!(result.currency, "USD");
    }

    #[test]
    fn summary_with_discount() {
        let items = vec![
            Item::new("n0", 1000, 10),
            Item::new("n1", 1000, 10),
            Item::new("n2", 1000, 10),
        ];
        let result = summary(&items);
        assert_eq!(result.total_cents, 28500);
        assert_eq!(result.average_cents, 9500);
    }

    #[test]
    fn summary_average_over_lines() {
        let items = vec![Item::new("a", 300, 1), Item::new("b", 500, 1)];
        assert_eq!(summary(&items).average_cents, 400);
    }

    #[test]
    fn summary_keeps_item_currency() {
        let item = Item {
            currency: "EUR".to_string(),
            ..Item::new("a", 400, 2)
        };
        assert_eq!(summary(&[item]).currency, "EUR");
    }
}
