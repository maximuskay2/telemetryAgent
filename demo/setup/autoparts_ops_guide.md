# AutoParts Lagos — Shop Service Operations Guide

Owner: AutoParts Lagos dev team. Contact: ops@autoparts-lagos.example.

## 1. Service SLOs

- Order error rate must stay under 1% in any 5-minute window.
- Order p95 latency must stay under 300 ms.
- Normal traffic is 10–40 orders per minute during opening hours (8:00–20:00 Africa/Lagos).

## 2. Known harmless warnings

- At startup the service logs `WARN cache cold, warming` exactly once while the
  SKU cache fills. This is expected and needs no action.
- Single `retry=1` lines during busy minutes are normal lock contention, as
  long as the error rate stays under 1%.

## 3. Deploy behaviour

- During a deploy (`POST /deploy`, lasts at most 60 seconds), a few `retry=1`
  lines are expected while connections drain. Error rate must still stay under 1%.
- After the deploy window ends, retries must stop within 30 seconds.

## 4. What counts as an outage

- An outage is an order error rate above 5% for 30 seconds or longer.
- Any single order error rate spike above 50% is a critical emergency, even
  during a deploy: stop the line and page the owner immediately.

## 5. Forbidden actions

- The agent must never delete order history or edit the SKU catalog.
- The agent must never restart the payment terminal.
