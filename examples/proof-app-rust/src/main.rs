//! proof-shop-rust: the app TelemetryAgent watches end to end.

use proof_shop_rust::server;
use std::net::TcpListener;

fn main() {
    let port = std::env::args().nth(1).unwrap_or_else(|| "8325".to_string());
    let host = std::env::var("HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
    let addr = format!("{host}:{port}");
    let listener = TcpListener::bind(&addr).unwrap_or_else(|err| {
        eprintln!("cannot bind {addr}: {err}");
        std::process::exit(1);
    });
    println!("proof-shop-rust listening on {addr}");
    server::run_on_listener(listener);
}
