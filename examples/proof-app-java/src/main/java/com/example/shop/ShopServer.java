package com.example.shop;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Proof shop HTTP API (JDK only): the app TelemetryAgent watches end to end. */
public final class ShopServer {
    private ShopServer() {}

    public static HttpServer create(int port) throws IOException {
        return create("127.0.0.1", port);
    }

    public static HttpServer create(String host, int port) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress(host, port), 0);
        server.createContext("/health", exchange -> {
            send(exchange, 200, Map.of("status", "ok"));
        });
        server.createContext("/checkout", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                send(exchange, 404, Map.of("detail", "not found"));
                return;
            }
            try {
                String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                List<Cart.Item> items = parseItems(body);
                if (items == null) {
                    send(exchange, 422, Map.of("detail", "invalid items"));
                    return;
                }
                // No try/except on purpose: the empty-cart ArithmeticException
                // must crash with a full stack trace so the forwarder ships
                // it to TelemetryAgent.
                Cart.Summary summary = Cart.summary(items);
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("lines", summary.lines());
                out.put("subtotal", summary.subtotalCents() / 100.0);
                out.put("discount", summary.discountCents() / 100.0);
                out.put("total", summary.totalCents() / 100.0);
                out.put("average_item_price", summary.averageCents() / 100.0);
                out.put("currency", summary.currency());
                send(exchange, 200, out);
            } catch (Exception e) {
                e.printStackTrace(); // the production trace
                send(exchange, 500, Map.of("detail", "internal error"));
            }
        });
        return server;
    }

    /** Returns null when the body fails validation (→ 422). */
    static List<Cart.Item> parseItems(String body) {
        final Object root;
        try {
            root = Json.parse(body.isEmpty() ? "{}" : body);
        } catch (IllegalArgumentException e) {
            return null;
        }
        if (!(root instanceof Map<?, ?> map)) {
            return null;
        }
        Object rawItems = map.containsKey("items") ? map.get("items") : List.of();
        if (!(rawItems instanceof List<?> list)) {
            return null;
        }
        List<Cart.Item> items = new ArrayList<>();
        for (Object raw : list) {
            if (!(raw instanceof Map<?, ?> item)) {
                return null;
            }
            if (!(item.get("name") instanceof String name) || name.isEmpty()) {
                return null;
            }
            if (!(item.get("price") instanceof Number price) || price.doubleValue() < 0) {
                return null;
            }
            if (!(item.get("qty") instanceof Number qty)
                    || qty.doubleValue() != Math.rint(qty.doubleValue())
                    || qty.intValue() < 0) {
                return null;
            }
            Object currency = item.containsKey("currency") ? item.get("currency") : "USD";
            if (!(currency instanceof String)) {
                return null;
            }
            items.add(new Cart.Item(
                    name, Math.round(price.doubleValue() * 100), qty.intValue(), (String) currency));
        }
        return items;
    }

    static void send(com.sun.net.httpserver.HttpExchange exchange, int status, Map<String, Object> obj)
            throws IOException {
        byte[] bytes = Json.stringify(obj).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("content-type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws IOException {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 8322;
        String host = System.getenv().getOrDefault("HOST", "127.0.0.1");
        HttpServer server = create(host, port);
        server.start();
        System.out.println("proof-shop-java listening on " + host + ":" + port);
    }
}
