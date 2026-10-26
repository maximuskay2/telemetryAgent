"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type LogEvent = {
  id: string;
  timestamp: string;
  source: string;
  message: string;
  level: string;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [message, setMessage] = useState("");
  const [source, setSource] = useState("terminal");
  const [connection, setConnection] = useState("connecting");
  const [error, setError] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const socket = new WebSocket(`${apiUrl.replace(/^http/, "ws")}/api/ws`);
    socket.onopen = () => setConnection("connected");
    socket.onclose = () => setConnection("disconnected");
    socket.onerror = () => setConnection("disconnected");
    socket.onmessage = (event) => {
      try {
        const logEvent = JSON.parse(event.data) as LogEvent;
        setEvents((current) => [...current.slice(-199), logEvent]);
      } catch {
        setError("Received an invalid event from the API.");
      }
    };
    return () => socket.close();
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [events]);

  async function submitLog(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = message.trim();
    if (!text) return;
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/logs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, source }),
      });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      setMessage("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit log.");
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OBSERVABILITY / LIVE FEED</p>
          <h1>Telemetry Agent</h1>
        </div>
        <div className={`status ${connection}`}>
          <span className="status-dot" />
          {connection}
        </div>
      </header>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">STREAM</p>
            <h2>Incoming events</h2>
          </div>
          <span className="counter">{events.length} events</span>
        </div>
        <div className="event-list" ref={listRef} aria-live="polite">
          {events.length === 0 ? (
            <div className="empty">
              <span className="prompt-mark">&gt;_</span>
              <p>Waiting for telemetry</p>
              <span>Submit a log entry below or POST to the API.</span>
            </div>
          ) : (
            events.map((item) => (
              <article className="event" key={item.id}>
                <time>{new Date(item.timestamp).toLocaleTimeString()}</time>
                <span className={`level ${item.level.toLowerCase()}`}>
                  {item.level}
                </span>
                <span className="source">{item.source}</span>
                <p>{item.message}</p>
              </article>
            ))
          )}
        </div>
      </section>

      <form className="composer" onSubmit={submitLog}>
        <label htmlFor="source">Source</label>
        <input
          id="source"
          value={source}
          onChange={(event) => setSource(event.target.value)}
          maxLength={100}
        />
        <label htmlFor="message">Log message</label>
        <input
          id="message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Type a log message..."
          maxLength={4000}
        />
        <button type="submit">Send event</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      <footer>Local-first telemetry · API {apiUrl}</footer>
    </main>
  );
}
