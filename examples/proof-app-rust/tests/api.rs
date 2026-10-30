//! Proof-shop API suite: exercises the HTTP layer over raw TCP against an
//! ephemeral port.

use proof_shop_rust::server::{self, JsonVal};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};

fn start_server() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    let port = listener.local_addr().expect("addr").port();
    std::thread::spawn(move || server::run_on_listener(listener));
    port
}

fn request(port: u16, raw: &str) -> (u16, String) {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).expect("connect");
    stream.write_all(raw.as_bytes()).expect("write");
    let mut buf = Vec::new();
    stream.read_to_end(&mut buf).expect("read");
    let text = String::from_utf8(buf).expect("utf-8");
    let (head, body) = text.split_once("\r\n\r\n").expect("head/body");
    let code: u16 = head
        .lines()
        .next()
        .expect("status")
        .split_whitespace()
        .nth(1)
        .expect("code")
        .parse()
        .expect("code int");
    (code, body.to_string())
}

fn post_checkout(port: u16, body: &str) -> (u16, String) {
    request(
        port,
        &format!(
            "POST /checkout HTTP/1.1\r\nhost: x\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
            body.len(),
            body
        ),
    )
}

fn get(port: u16, path: &str) -> (u16, String) {
    request(
        port,
        &format!("GET {path} HTTP/1.1\r\nhost: x\r\nconnection: close\r\n\r\n"),
    )
}

fn json_obj(body: &str) -> HashMap<String, JsonVal> {
    match server::parse_json(body).expect("parse") {
        JsonVal::Obj(map) => map,
        other => panic!("want object, got {other:?}"),
    }
}

fn num(map: &HashMap<String, JsonVal>, key: &str) -> f64 {
    match map.get(key).expect("key") {
        JsonVal::Num(value) => *value,
        other => panic!("want num for {key}, got {other:?}"),
    }
}

#[test]
fn health() {
    let (code, body) = get(start_server(), "/health");
    assert_eq!(code, 200);
    assert_eq!(
        json_obj(&body).get("status"),
        Some(&JsonVal::Str("ok".to_string()))
    );
}

#[test]
fn checkout_ok() {
    let (code, body) = post_checkout(
        start_server(),
        r#"{"items": [{"name": "a", "price": 2.0, "qty": 2}]}"#,
    );
    assert_eq!(code, 200);
    assert_eq!(num(&json_obj(&body), "total"), 4.0);
}

#[test]
fn checkout_validates_price() {
    let (code, _) = post_checkout(
        start_server(),
        r#"{"items": [{"name": "a", "price": -1, "qty": 1}]}"#,
    );
    assert_eq!(code, 422);
}

#[test]
fn checkout_validates_name() {
    let (code, _) = post_checkout(
        start_server(),
        r#"{"items": [{"name": "", "price": 1, "qty": 1}]}"#,
    );
    assert_eq!(code, 422);
}

#[test]
fn checkout_bulk_order() {
    let (code, body) = post_checkout(
        start_server(),
        r#"{"items": [{"name": "n0", "price": 10.0, "qty": 10}, {"name": "n1", "price": 10.0, "qty": 10}, {"name": "n2", "price": 10.0, "qty": 10}]}"#,
    );
    assert_eq!(code, 200);
    assert_eq!(num(&json_obj(&body), "discount"), 15.0);
}

#[test]
fn checkout_single_bulk_line_has_no_discount() {
    let (code, body) = post_checkout(
        start_server(),
        r#"{"items": [{"name": "a", "price": 1.0, "qty": 25}]}"#,
    );
    assert_eq!(code, 200);
    assert_eq!(num(&json_obj(&body), "discount"), 0.0);
}

#[test]
fn checkout_zero_qty_line() {
    let (code, body) = post_checkout(
        start_server(),
        r#"{"items": [{"name": "a", "price": 3.0, "qty": 0}]}"#,
    );
    assert_eq!(code, 200);
    assert_eq!(num(&json_obj(&body), "total"), 0.0);
}

#[test]
fn unknown_route_is_404() {
    let (code, _) = get(start_server(), "/nope");
    assert_eq!(code, 404);
}
