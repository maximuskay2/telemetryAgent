# proof-shop-java — the Java app TelemetryAgent proves itself on

A tiny Maven cart service (JDK `HttpServer`, JUnit 5, no runtime deps)
with one real bug: checking out an **empty cart** crashes with
`ArithmeticException: / by zero` (`Cart.java`, `summary()` divides by
`items.size()`). The suite (20 tests) is green on the buggy code — the
empty cart is the case nobody tested, and the one TelemetryAgent writes,
proves, and fixes.

Wire shape matches `examples/proof-app` (Python): `POST /checkout` with
`{"items": [{"name", "price", "qty", "currency"?}]}` → `{"lines",
"subtotal", "discount", "total", "average_item_price", "currency"}`.
Money is integer cents inside, dollars on the wire.

## Run locally

```bash
mvn -q test                        # 20 passed
./trigger.sh                       # compiles, starts its own server,
                                   # POSTs {"items": []} -> 500 + the real
                                   # JVM stack trace, printed
```

## Suite in the sandbox image

```bash
docker run --rm -v "$PWD:/app" -w /app maven:3.9-eclipse-temurin-21 \
  mvn -B -q test
```

Servers bind `127.0.0.1` by default; set `HOST=0.0.0.0` to run in a container or on Railway.

## Ship logs to TelemetryAgent

Run the server with stderr to a file and point the forwarder at it, same
as the Python app (`/connect` prints the one-liner):

```bash
mvn -q compile
java -cp target/classes com.example.shop.ShopServer 8322 > app.log 2>&1 &
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file app.log --service proof-shop-java
```

## What the proof run does

1. `trigger.sh` → JVM `ArithmeticException` trace → forwarder →
   TelemetryAgent.
2. Agent locates `Cart.java`, reproduces in the JVM sandbox, patches the
   empty-cart guard, proves the suite stays green, opens a PR here.
3. Merge → redeploy → `trigger.sh` returns 200 with
   `average_item_price: 0.0`.
