# proof-shop-php — the PHP app TelemetryAgent proves itself on

A tiny Composer cart service (built-in web server, PHPUnit, no runtime
deps) with one real bug: checking out an **empty cart** crashes with
`DivisionByZeroError` (`src/Cart.php`, `summary()` divides by
`count($items)`). The suite (20 tests) is green on the buggy code — the
empty cart is the case nobody tested, and the one TelemetryAgent writes,
proves, and fixes.

Wire shape matches `examples/proof-app` (Python): `POST /checkout` with
`{"items": [{"name", "price", "qty", "currency"?}]}` → `{"lines",
"subtotal", "discount", "total", "average_item_price", "currency"}`.
Money is integer cents inside, dollars on the wire.

## Run locally

```bash
composer install --no-interaction --no-progress
vendor/bin/phpunit               # 20 passed
./trigger.sh                     # starts its own server, POSTs {"items": []}
                                 # -> 500 + the real fatal + stack trace
```

(`-d display_errors=stderr`: fatals go to stderr for the forwarder,
never into the response body — same flags in `trigger.sh` and below.)

## Suite in the sandbox image

```bash
docker run --rm -v "$PWD:/app" -w /app php:8.3-cli \
  sh -c 'composer install --no-interaction --no-progress && vendor/bin/phpunit'
```

(The sandbox `php` image ships Composer; stock `php:8.3-cli` needs it
installed first.)

Servers bind `127.0.0.1` by default; set `HOST=0.0.0.0` to run in a container or on Railway.

## Ship logs to TelemetryAgent

Run the server with stderr to a file and point the forwarder at it, same
as the Python app (`/connect` prints the one-liner):

```bash
php -d display_errors=stderr -d html_errors=0 -S 127.0.0.1:8326 -t public public/index.php > app.log 2>&1 &
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file app.log --service proof-shop-php
```

## What the proof run does

1. `trigger.sh` → PHP fatal trace → forwarder → TelemetryAgent.
2. Agent locates `src/Cart.php`, reproduces in the PHP sandbox, patches
   the empty-cart guard, proves the suite stays green, opens a PR here.
3. Merge → redeploy → `trigger.sh` returns 200 with
   `average_item_price: 0.0`.
