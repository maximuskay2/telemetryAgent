package com.example.shop

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import kotlin.math.floor
import kotlin.math.round

/** Proof shop HTTP API (JDK only): the app TelemetryAgent watches end to end. */
object ShopServer {
    fun create(port: Int): HttpServer = create("127.0.0.1", port)

    fun create(host: String, port: Int): HttpServer {
        val server = HttpServer.create(InetSocketAddress(host, port), 0)
        server.createContext("/health") { exchange ->
            send(exchange, 200, mapOf("status" to "ok"))
        }
        server.createContext("/checkout") { exchange ->
            if (!exchange.requestMethod.equals("POST", ignoreCase = true)) {
                send(exchange, 404, mapOf("detail" to "not found"))
                return@createContext
            }
            try {
                val body = exchange.requestBody.readAllBytes().toString(Charsets.UTF_8)
                val items = parseItems(body)
                if (items == null) {
                    send(exchange, 422, mapOf("detail" to "invalid items"))
                    return@createContext
                }
                // No try/except on purpose: the empty-cart ArithmeticException
                // must crash with a full stack trace so the forwarder ships
                // it to TelemetryAgent.
                val summary = Cart.summary(items)
                send(
                    exchange,
                    200,
                    linkedMapOf(
                        "lines" to summary.lines,
                        "subtotal" to summary.subtotalCents / 100.0,
                        "discount" to summary.discountCents / 100.0,
                        "total" to summary.totalCents / 100.0,
                        "average_item_price" to summary.averageCents / 100.0,
                        "currency" to summary.currency,
                    ),
                )
            } catch (e: Exception) {
                e.printStackTrace() // the production trace
                send(exchange, 500, mapOf("detail" to "internal error"))
            }
        }
        return server
    }

    /** Returns null when the body fails validation (→ 422). */
    fun parseItems(body: String): List<Cart.Item>? {
        val root = try {
            asObj(Json.parse(body.ifEmpty { "{}" })) ?: return null
        } catch (e: IllegalArgumentException) {
            return null
        }
        val rawItems = if (root.containsKey("items")) root["items"] else listOf<Any?>()
        if (rawItems !is List<*>) return null
        return rawItems.map { raw ->
            val item = asObj(raw) ?: return null
            val name = item["name"] as? String ?: return null
            if (name.isEmpty()) return null
            val price = (item["price"] as? Number)?.toDouble() ?: return null
            if (price < 0) return null
            val qty = (item["qty"] as? Number)?.toDouble() ?: return null
            if (qty != floor(qty) || qty < 0) return null
            val currency = (item["currency"] as? String) ?: "USD"
            Cart.Item(name, round(price * 100).toLong(), qty.toInt(), currency)
        }
    }

    /** Json.obj() always builds String-keyed maps, so this cast is safe. */
    @Suppress("UNCHECKED_CAST")
    private fun asObj(value: Any?): Map<String, Any?>? = value as? Map<String, Any?>

    fun send(exchange: HttpExchange, status: Int, obj: Map<String, Any?>) {
        val bytes = Json.stringify(obj).toByteArray(Charsets.UTF_8)
        exchange.responseHeaders.set("content-type", "application/json")
        exchange.sendResponseHeaders(status, bytes.size.toLong())
        exchange.responseBody.use { it.write(bytes) }
    }
}

fun main(args: Array<String>) {
    val port = if (args.isNotEmpty()) args[0].toInt() else 8323
    val host = System.getenv("HOST") ?: "127.0.0.1"
    val server = ShopServer.create(host, port)
    server.start()
    println("proof-shop-kotlin listening on $host:$port")
}
