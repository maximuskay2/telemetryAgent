// Proof shop HTTP API (stdlib only): the app TelemetryAgent watches end to end.
import http from "node:http";
import { summary } from "./cart.js";

function send(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function validItem(it) {
  return (
    it !== null &&
    typeof it === "object" &&
    typeof it.name === "string" &&
    it.name.length > 0 &&
    typeof it.price === "number" &&
    it.price >= 0 &&
    Number.isInteger(it.qty) &&
    it.qty >= 0
  );
}

export function createServer() {
  return http.createServer((req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      send(res, 200, { status: "ok" });
      return;
    }
    if (req.method === "POST" && req.url === "/checkout") {
      let raw = "";
      req.on("data", (chunk) => {
        raw += chunk;
      });
      req.on("end", () => {
        try {
          const payload = JSON.parse(raw || "{}");
          const items = payload.items ?? [];
          if (!Array.isArray(items) || !items.every(validItem)) {
            send(res, 422, { detail: "invalid items" });
            return;
          }
          // No try/except on purpose: the empty-cart TypeError must crash
          // with a full stack so the forwarder ships it to TelemetryAgent.
          send(res, 200, summary(items));
        } catch (err) {
          console.error(err.stack); // the production trace
          send(res, 500, { detail: "internal error" });
        }
      });
      return;
    }
    send(res, 404, { detail: "not found" });
  });
}

if (process.argv[1] && process.argv[1].endsWith("server.js")) {
  const port = Number(process.argv[2] ?? 8321);
  const host = process.env.HOST ?? "127.0.0.1";
  createServer().listen(port, host, () => {
    console.log(`proof-shop-node listening on ${host}:${port}`);
  });
}
