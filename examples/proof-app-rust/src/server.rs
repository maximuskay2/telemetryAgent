//! Proof shop HTTP API (std only): the app TelemetryAgent watches end to end.
//!
//! Minimal HTTP/1.1 over `TcpListener` plus minimal JSON for the proof
//! shop's fixed shapes (fixture-only, not real parsers).

use crate::cart::{self, Item};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};

/// Minimal JSON value. Numbers always parse as `f64`.
#[derive(Debug, Clone, PartialEq)]
pub enum JsonVal {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<JsonVal>),
    Obj(HashMap<String, JsonVal>),
}

/// Parse one JSON value (fixture-only).
pub fn parse_json(text: &str) -> Result<JsonVal, String> {
    let mut parser = Parser {
        chars: text.as_bytes(),
        pos: 0,
    };
    let value = parser.value()?;
    parser.ws();
    if !parser.end() {
        return Err("trailing characters in JSON".to_string());
    }
    Ok(value)
}

struct Parser<'a> {
    chars: &'a [u8],
    pos: usize,
}

impl Parser<'_> {
    fn end(&self) -> bool {
        self.pos >= self.chars.len()
    }

    fn peek(&self) -> u8 {
        self.chars[self.pos]
    }

    fn ws(&mut self) {
        while !self.end() && (self.peek() as char).is_whitespace() {
            self.pos += 1;
        }
    }

    fn expect(&mut self, byte: u8) -> Result<(), String> {
        if self.end() || self.peek() != byte {
            return Err(format!("expected '{}' at {}", byte as char, self.pos));
        }
        self.pos += 1;
        Ok(())
    }

    fn value(&mut self) -> Result<JsonVal, String> {
        self.ws();
        if self.end() {
            return Err("unexpected end of JSON".to_string());
        }
        match self.peek() {
            b'{' => Ok(JsonVal::Obj(self.object()?)),
            b'[' => Ok(JsonVal::Arr(self.array()?)),
            b'"' => Ok(JsonVal::Str(self.string()?)),
            b't' => self.literal("true", JsonVal::Bool(true)),
            b'f' => self.literal("false", JsonVal::Bool(false)),
            b'n' => self.literal("null", JsonVal::Null),
            _ => Ok(JsonVal::Num(self.number()?)),
        }
    }

    fn object(&mut self) -> Result<HashMap<String, JsonVal>, String> {
        let mut map = HashMap::new();
        self.pos += 1; // {
        self.ws();
        if !self.end() && self.peek() == b'}' {
            self.pos += 1;
            return Ok(map);
        }
        loop {
            self.ws();
            let key = self.string()?;
            self.ws();
            self.expect(b':')?;
            map.insert(key, self.value()?);
            self.ws();
            if !self.end() && self.peek() == b',' {
                self.pos += 1;
                continue;
            }
            self.expect(b'}')?;
            return Ok(map);
        }
    }

    fn array(&mut self) -> Result<Vec<JsonVal>, String> {
        let mut items = Vec::new();
        self.pos += 1; // [
        self.ws();
        if !self.end() && self.peek() == b']' {
            self.pos += 1;
            return Ok(items);
        }
        loop {
            items.push(self.value()?);
            self.ws();
            if !self.end() && self.peek() == b',' {
                self.pos += 1;
                continue;
            }
            self.expect(b']')?;
            return Ok(items);
        }
    }

    fn string(&mut self) -> Result<String, String> {
        self.expect(b'"')?;
        let mut out = Vec::new();
        loop {
            if self.end() {
                return Err("unterminated string".to_string());
            }
            let byte = self.peek();
            self.pos += 1;
            if byte == b'"' {
                return String::from_utf8(out).map_err(|_| "bad utf-8".to_string());
            }
            if byte == b'\\' {
                if self.end() {
                    return Err("unterminated escape".to_string());
                }
                let esc = self.peek();
                self.pos += 1;
                match esc {
                    b'n' => out.push(b'\n'),
                    b't' => out.push(b'\t'),
                    b'r' => out.push(b'\r'),
                    b'"' => out.push(b'"'),
                    b'\\' => out.push(b'\\'),
                    b'/' => out.push(b'/'),
                    b'u' => {
                        if self.pos + 4 > self.chars.len() {
                            return Err("bad \\u escape".to_string());
                        }
                        let hex = std::str::from_utf8(&self.chars[self.pos..self.pos + 4])
                            .map_err(|_| "bad \\u escape".to_string())?;
                        let code = u32::from_str_radix(hex, 16)
                            .map_err(|_| "bad \\u escape".to_string())?;
                        let ch = char::from_u32(code).ok_or("bad \\u escape".to_string())?;
                        let mut buf = [0u8; 4];
                        out.extend_from_slice(ch.encode_utf8(&mut buf).as_bytes());
                        self.pos += 4;
                    }
                    _ => return Err(format!("bad escape \\{}", esc as char)),
                }
            } else {
                out.push(byte);
            }
        }
    }

    fn literal(&mut self, word: &str, value: JsonVal) -> Result<JsonVal, String> {
        if self.chars[self.pos..].starts_with(word.as_bytes()) {
            self.pos += word.len();
            Ok(value)
        } else {
            Err(format!("bad literal at {}", self.pos))
        }
    }

    fn number(&mut self) -> Result<f64, String> {
        let start = self.pos;
        while !self.end() && b"-+0123456789.eE".contains(&self.peek()) {
            self.pos += 1;
        }
        std::str::from_utf8(&self.chars[start..self.pos])
            .ok()
            .and_then(|text| text.parse::<f64>().ok())
            .ok_or_else(|| format!("bad number at {start}"))
    }
}

/// Render cents as exact dollars (`800 -> "8.00"`).
fn dollars(cents: i64) -> String {
    format!("{}.{:02}", cents / 100, (cents % 100).abs())
}

fn escape(text: &str) -> String {
    text.replace('\\', "\\\\").replace('"', "\\\"")
}

/// Parse + validate a checkout body. `None` means 422.
fn parse_items(body: &str) -> Option<Vec<Item>> {
    let root = parse_json(if body.is_empty() { "{}" } else { body }).ok()?;
    let JsonVal::Obj(map) = root else {
        return None;
    };
    let raw_items = match map.get("items") {
        None => Vec::new(),
        Some(JsonVal::Arr(items)) => items.clone(),
        Some(_) => return None,
    };
    let mut items = Vec::with_capacity(raw_items.len());
    for raw in &raw_items {
        let JsonVal::Obj(item) = raw else {
            return None;
        };
        let JsonVal::Str(name) = item.get("name")? else {
            return None;
        };
        if name.is_empty() {
            return None;
        }
        let JsonVal::Num(price) = item.get("price")? else {
            return None;
        };
        if *price < 0.0 {
            return None;
        }
        let JsonVal::Num(qty) = item.get("qty")? else {
            return None;
        };
        if qty.fract() != 0.0 || *qty < 0.0 {
            return None;
        }
        let currency = match item.get("currency") {
            None => "USD".to_string(),
            Some(JsonVal::Str(currency)) => currency.clone(),
            Some(_) => return None,
        };
        items.push(Item {
            name: name.clone(),
            price_cents: (price * 100.0).round() as i64,
            qty: *qty as i64,
            currency,
        });
    }
    Some(items)
}

fn reason(code: u16) -> &'static str {
    match code {
        200 => "OK",
        404 => "Not Found",
        422 => "Unprocessable Entity",
        _ => "Internal Server Error",
    }
}

fn respond(stream: &mut TcpStream, code: u16, body: &str) {
    let head = format!(
        "HTTP/1.1 {code} {}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n",
        reason(code),
        body.len()
    );
    let _ = stream.write_all(head.as_bytes());
    let _ = stream.write_all(body.as_bytes());
}

/// Route one request. A checkout panic unwinds to the connection thread,
/// which answers 500 after the panic hook prints the real trace.
fn handle(method: &str, path: &str, body: &str) -> (u16, String) {
    if method == "GET" && path == "/health" {
        return (200, r#"{"status":"ok"}"#.to_string());
    }
    if method == "POST" && path == "/checkout" {
        let Some(items) = parse_items(body) else {
            return (422, r#"{"detail":"invalid items"}"#.to_string());
        };
        // No catch_unwind here on purpose: the empty-cart panic must crash
        // with a full trace so the forwarder ships it to TelemetryAgent.
        let summary = cart::summary(&items);
        let body = format!(
            r#"{{"lines":{},"subtotal":{},"discount":{},"total":{},"average_item_price":{},"currency":"{}"}}"#,
            summary.lines,
            dollars(summary.subtotal_cents),
            dollars(summary.discount_cents),
            dollars(summary.total_cents),
            dollars(summary.average_cents),
            escape(&summary.currency),
        );
        return (200, body);
    }
    (404, r#"{"detail":"not found"}"#.to_string())
}

fn handle_connection(stream: &mut TcpStream) {
    let mut raw = Vec::new();
    let mut byte = [0u8; 1];
    // Read headers (requests here are small; 64 KiB cap).
    loop {
        match stream.read(&mut byte) {
            Ok(0) | Err(_) => return,
            Ok(_) => {
                raw.push(byte[0]);
                if raw.len() > 65536 {
                    return;
                }
                if raw.ends_with(b"\r\n\r\n") {
                    break;
                }
            }
        }
    }
    let head = String::from_utf8_lossy(&raw);
    let mut lines = head.lines();
    let request_line = lines.next().unwrap_or("");
    let mut parts = request_line.split_whitespace();
    let method = parts.next().unwrap_or("").to_string();
    let path = parts.next().unwrap_or("").to_string();
    let mut content_length: usize = 0;
    for line in lines {
        if let Some(value) = line.strip_prefix("content-length:") {
            content_length = value.trim().parse().unwrap_or(0);
        } else if let Some(value) = line.strip_prefix("Content-Length:") {
            content_length = value.trim().parse().unwrap_or(0);
        }
    }
    let mut body = vec![0u8; content_length];
    if content_length > 0 {
        if stream.read_exact(&mut body).is_err() {
            return;
        }
    }
    let body_text = String::from_utf8_lossy(&body);
    let (code, response) = handle(&method, &path, &body_text);
    respond(stream, code, &response);
}

/// Serve forever on an already-bound listener (tests bind port 0).
pub fn run_on_listener(listener: TcpListener) {
    for stream in listener.incoming() {
        let Ok(mut stream) = stream else {
            continue;
        };
        std::thread::Builder::new()
            .name("proof-shop-worker".to_string())
            .spawn(move || {
                let survived = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    handle_connection(&mut stream);
                }));
                if survived.is_err() {
                    // The panic hook already printed the real trace.
                    respond(&mut stream, 500, r#"{"detail":"internal error"}"#);
                }
            })
            .expect("spawn worker");
    }
}
