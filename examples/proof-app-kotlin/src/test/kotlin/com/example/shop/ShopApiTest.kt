package com.example.shop

import com.sun.net.httpserver.HttpServer
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.Test

/** Proof-shop API suite: exercises the HTTP layer on an ephemeral port. */
class ShopApiTest {
    companion object {
        private lateinit var server: HttpServer
        private lateinit var base: String
        private val client = HttpClient.newHttpClient()

        @JvmStatic
        @BeforeAll
        fun start() {
            server = ShopServer.create(0)
            server.start()
            base = "http://127.0.0.1:" + server.address.port
        }

        @JvmStatic
        @AfterAll
        fun stop() {
            server.stop(0)
        }

        private fun post(path: String, body: String): HttpResponse<String> {
            val request = HttpRequest.newBuilder(URI.create(base + path))
                .header("content-type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build()
            return client.send(request, HttpResponse.BodyHandlers.ofString())
        }

        @Suppress("UNCHECKED_CAST")
        private fun json(body: String): Map<String, Any?> = Json.parse(body) as Map<String, Any?>
    }

    @Test
    fun `health`() {
        val request = HttpRequest.newBuilder(URI.create("$base/health")).GET().build()
        val response = client.send(request, HttpResponse.BodyHandlers.ofString())
        assertEquals(200, response.statusCode())
        assertEquals("ok", json(response.body())["status"])
    }

    @Test
    fun `checkout ok`() {
        val response = post("/checkout", """{"items": [{"name": "a", "price": 2.0, "qty": 2}]}""")
        assertEquals(200, response.statusCode())
        assertEquals(4.0, json(response.body())["total"])
    }

    @Test
    fun `checkout validates price`() {
        val response = post("/checkout", """{"items": [{"name": "a", "price": -1, "qty": 1}]}""")
        assertEquals(422, response.statusCode())
    }

    @Test
    fun `checkout validates name`() {
        val response = post("/checkout", """{"items": [{"name": "", "price": 1, "qty": 1}]}""")
        assertEquals(422, response.statusCode())
    }

    @Test
    fun `checkout bulk order`() {
        val response = post(
            "/checkout",
            """{"items": [{"name": "n0", "price": 10.0, "qty": 10},""" +
                """ {"name": "n1", "price": 10.0, "qty": 10},""" +
                """ {"name": "n2", "price": 10.0, "qty": 10}]}""",
        )
        assertEquals(200, response.statusCode())
        assertEquals(15.0, json(response.body())["discount"])
    }

    @Test
    fun `checkout single bulk line has no discount`() {
        val response =
            post("/checkout", """{"items": [{"name": "a", "price": 1.0, "qty": 25}]}""")
        assertEquals(200, response.statusCode())
        assertEquals(0.0, json(response.body())["discount"])
    }

    @Test
    fun `checkout zero qty line`() {
        val response =
            post("/checkout", """{"items": [{"name": "a", "price": 3.0, "qty": 0}]}""")
        assertEquals(200, response.statusCode())
        assertEquals(0.0, json(response.body())["total"])
    }

    @Test
    fun `unknown route is 404`() {
        val request = HttpRequest.newBuilder(URI.create("$base/nope")).GET().build()
        val response = client.send(request, HttpResponse.BodyHandlers.ofString())
        assertEquals(404, response.statusCode())
    }
}
