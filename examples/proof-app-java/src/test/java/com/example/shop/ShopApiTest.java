package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/** Proof-shop API suite: exercises the HTTP layer on an ephemeral port. */
class ShopApiTest {

    private static HttpServer server;
    private static String base;
    private static final HttpClient client = HttpClient.newHttpClient();

    @BeforeAll
    static void start() throws IOException {
        server = ShopServer.create(0);
        server.start();
        base = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterAll
    static void stop() {
        server.stop(0);
    }

    private static HttpResponse<String> post(String path, String body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create(base + path))
                .header("content-type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> json(String body) {
        return (Map<String, Object>) Json.parse(body);
    }

    @Test
    void health() throws Exception {
        HttpRequest request =
                HttpRequest.newBuilder(URI.create(base + "/health")).GET().build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode());
        assertEquals("ok", json(response.body()).get("status"));
    }

    @Test
    void checkoutOk() throws Exception {
        HttpResponse<String> response =
                post("/checkout", "{\"items\": [{\"name\": \"a\", \"price\": 2.0, \"qty\": 2}]}");
        assertEquals(200, response.statusCode());
        assertEquals(4.0, json(response.body()).get("total"));
    }

    @Test
    void checkoutValidatesPrice() throws Exception {
        HttpResponse<String> response =
                post("/checkout", "{\"items\": [{\"name\": \"a\", \"price\": -1, \"qty\": 1}]}");
        assertEquals(422, response.statusCode());
    }

    @Test
    void checkoutValidatesName() throws Exception {
        HttpResponse<String> response =
                post("/checkout", "{\"items\": [{\"name\": \"\", \"price\": 1, \"qty\": 1}]}");
        assertEquals(422, response.statusCode());
    }

    @Test
    void checkoutBulkOrder() throws Exception {
        HttpResponse<String> response = post(
                "/checkout",
                "{\"items\": [{\"name\": \"n0\", \"price\": 10.0, \"qty\": 10},"
                        + " {\"name\": \"n1\", \"price\": 10.0, \"qty\": 10},"
                        + " {\"name\": \"n2\", \"price\": 10.0, \"qty\": 10}]}");
        assertEquals(200, response.statusCode());
        assertEquals(15.0, json(response.body()).get("discount"));
    }

    @Test
    void checkoutSingleBulkLineHasNoDiscount() throws Exception {
        HttpResponse<String> response =
                post("/checkout", "{\"items\": [{\"name\": \"a\", \"price\": 1.0, \"qty\": 25}]}");
        assertEquals(200, response.statusCode());
        assertEquals(0.0, json(response.body()).get("discount"));
    }

    @Test
    void checkoutZeroQtyLine() throws Exception {
        HttpResponse<String> response =
                post("/checkout", "{\"items\": [{\"name\": \"a\", \"price\": 3.0, \"qty\": 0}]}");
        assertEquals(200, response.statusCode());
        assertEquals(0.0, json(response.body()).get("total"));
    }

    @Test
    void unknownRouteIs404() throws Exception {
        HttpRequest request =
                HttpRequest.newBuilder(URI.create(base + "/nope")).GET().build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        assertEquals(404, response.statusCode());
    }
}
