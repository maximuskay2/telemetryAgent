package com.example.shop

/**
 * Minimal JSON for the proof shop's fixed shapes (fixture-only, not a real
 * parser). Numbers always parse as [Double]; objects keep insertion order.
 */
object Json {
    fun parse(text: String): Any? {
        val parser = Parser(text)
        val value = parser.value()
        parser.ws()
        require(parser.end()) { "trailing characters in JSON" }
        return value
    }

    fun stringify(value: Any?): String = when (value) {
        null -> "null"
        is String -> "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
        is Boolean, is Number -> value.toString()
        is Map<*, *> -> value.entries.joinToString(",", "{", "}") { (k, v) ->
            "${stringify(k.toString())}:${stringify(v)}"
        }
        is List<*> -> value.joinToString(",", "[", "]") { stringify(it) }
        else -> throw IllegalArgumentException("cannot stringify $value")
    }

    private class Parser(val text: String) {
        var pos = 0

        fun end(): Boolean = pos >= text.length

        fun ws() {
            while (!end() && text[pos].isWhitespace()) pos++
        }

        fun value(): Any? {
            ws()
            require(!end()) { "unexpected end of JSON" }
            return when (text[pos]) {
                '{' -> obj()
                '[' -> array()
                '"' -> string()
                't' -> literal("true", true)
                'f' -> literal("false", false)
                'n' -> literal("null", null)
                else -> number()
            }
        }

        fun obj(): Map<String, Any?> {
            val map = linkedMapOf<String, Any?>()
            pos++ // {
            ws()
            if (!end() && text[pos] == '}') {
                pos++
                return map
            }
            while (true) {
                ws()
                val key = string()
                ws()
                expect(':')
                map[key] = value()
                ws()
                if (!end() && text[pos] == ',') {
                    pos++
                    continue
                }
                expect('}')
                return map
            }
        }

        fun array(): List<Any?> {
            val list = mutableListOf<Any?>()
            pos++ // [
            ws()
            if (!end() && text[pos] == ']') {
                pos++
                return list
            }
            while (true) {
                list.add(value())
                ws()
                if (!end() && text[pos] == ',') {
                    pos++
                    continue
                }
                expect(']')
                return list
            }
        }

        fun string(): String {
            expect('"')
            val out = StringBuilder()
            while (true) {
                require(!end()) { "unterminated string" }
                val c = text[pos++]
                if (c == '"') return out.toString()
                if (c == '\\') {
                    require(!end()) { "unterminated escape" }
                    out.append(
                        when (val e = text[pos++]) {
                            'n' -> '\n'
                            't' -> '\t'
                            'r' -> '\r'
                            'b' -> '\b'
                            'f' -> '\u000C'
                            'u' -> {
                                require(pos + 4 <= text.length) { "bad \\u escape" }
                                val code = text.substring(pos, pos + 4).toInt(16)
                                pos += 4
                                code.toChar()
                            }
                            else -> e
                        },
                    )
                } else {
                    out.append(c)
                }
            }
        }

        fun literal(word: String, value: Any?): Any? {
            require(text.startsWith(word, pos)) { "bad literal at $pos" }
            pos += word.length
            return value
        }

        fun number(): Double {
            val start = pos
            while (!end() && text[pos] in "-+0123456789.eE") pos++
            return text.substring(start, pos).toDoubleOrNull()
                ?: throw IllegalArgumentException("bad number at $start")
        }

        fun expect(c: Char) {
            require(!end() && text[pos] == c) { "expected '$c' at $pos" }
            pos++
        }
    }
}
