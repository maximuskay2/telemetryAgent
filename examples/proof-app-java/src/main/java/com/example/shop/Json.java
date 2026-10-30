package com.example.shop;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Minimal JSON for the proof shop's fixed shapes (fixture-only, not a real
 * parser). Numbers always parse as {@code Double}; objects keep insertion
 * order.
 */
public final class Json {
    private Json() {}

    public static Object parse(String text) {
        Parser parser = new Parser(text);
        Object value = parser.value();
        parser.ws();
        if (!parser.end()) {
            throw new IllegalArgumentException("trailing characters in JSON");
        }
        return value;
    }

    public static String stringify(Object value) {
        if (value == null) {
            return "null";
        } else if (value instanceof String s) {
            return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
        } else if (value instanceof Boolean || value instanceof Number) {
            return value.toString();
        } else if (value instanceof Map<?, ?> map) {
            StringBuilder out = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) {
                    out.append(",");
                }
                first = false;
                out.append(stringify(entry.getKey().toString()));
                out.append(":");
                out.append(stringify(entry.getValue()));
            }
            return out.append("}").toString();
        } else if (value instanceof List<?> list) {
            StringBuilder out = new StringBuilder("[");
            boolean first = true;
            for (Object item : list) {
                if (!first) {
                    out.append(",");
                }
                first = false;
                out.append(stringify(item));
            }
            return out.append("]").toString();
        }
        throw new IllegalArgumentException("cannot stringify " + value.getClass());
    }

    private static final class Parser {
        private final String text;
        private int pos;

        Parser(String text) {
            this.text = text;
        }

        boolean end() {
            return pos >= text.length();
        }

        void ws() {
            while (!end() && Character.isWhitespace(text.charAt(pos))) {
                pos++;
            }
        }

        Object value() {
            ws();
            if (end()) {
                throw new IllegalArgumentException("unexpected end of JSON");
            }
            char c = text.charAt(pos);
            return switch (c) {
                case '{' -> object();
                case '[' -> array();
                case '"' -> string();
                case 't' -> literal("true", Boolean.TRUE);
                case 'f' -> literal("false", Boolean.FALSE);
                case 'n' -> literal("null", null);
                default -> number();
            };
        }

        Map<String, Object> object() {
            Map<String, Object> map = new LinkedHashMap<>();
            pos++; // {
            ws();
            if (!end() && text.charAt(pos) == '}') {
                pos++;
                return map;
            }
            while (true) {
                ws();
                String key = string();
                ws();
                expect(':');
                map.put(key, value());
                ws();
                if (!end() && text.charAt(pos) == ',') {
                    pos++;
                    continue;
                }
                expect('}');
                return map;
            }
        }

        List<Object> array() {
            List<Object> list = new ArrayList<>();
            pos++; // [
            ws();
            if (!end() && text.charAt(pos) == ']') {
                pos++;
                return list;
            }
            while (true) {
                list.add(value());
                ws();
                if (!end() && text.charAt(pos) == ',') {
                    pos++;
                    continue;
                }
                expect(']');
                return list;
            }
        }

        String string() {
            expect('"');
            StringBuilder out = new StringBuilder();
            while (true) {
                if (end()) {
                    throw new IllegalArgumentException("unterminated string");
                }
                char c = text.charAt(pos++);
                if (c == '"') {
                    return out.toString();
                }
                if (c == '\\') {
                    if (end()) {
                        throw new IllegalArgumentException("unterminated escape");
                    }
                    char e = text.charAt(pos++);
                    out.append(switch (e) {
                        case 'n' -> '\n';
                        case 't' -> '\t';
                        case 'r' -> '\r';
                        case 'b' -> '\b';
                        case 'f' -> '\f';
                        case 'u' -> {
                            if (pos + 4 > text.length()) {
                                throw new IllegalArgumentException("bad \\u escape");
                            }
                            int code = Integer.parseInt(text.substring(pos, pos + 4), 16);
                            pos += 4;
                            yield (char) code;
                        }
                        default -> e;
                    });
                } else {
                    out.append(c);
                }
            }
        }

        Object literal(String word, Object value) {
            if (!text.startsWith(word, pos)) {
                throw new IllegalArgumentException("bad literal at " + pos);
            }
            pos += word.length();
            return value;
        }

        Double number() {
            int start = pos;
            while (!end() && "-+0123456789.eE".indexOf(text.charAt(pos)) >= 0) {
                pos++;
            }
            try {
                return Double.parseDouble(text.substring(start, pos));
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("bad number at " + start);
            }
        }

        void expect(char c) {
            if (end() || text.charAt(pos) != c) {
                throw new IllegalArgumentException("expected '" + c + "' at " + pos);
            }
            pos++;
        }
    }
}
