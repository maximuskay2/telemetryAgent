"use client";

import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../lib/api";
import { parseEvent, type StreamEvent } from "../types/api";

/**
 * Socket lifecycle: 2 s reconnect, typed dispatch, batching per animation
 * frame (order preserved). Invalid JSON calls onError; unknown-but-valid
 * frames are ignored, exactly like the old dashboard.
 */
export function useAgentStream({
  onEvent,
  onError,
}: {
  onEvent: (event: StreamEvent) => void;
  onError: (message: string) => void;
}) {
  const [connection, setConnection] = useState("connecting");
  const [reconnectKey, setReconnectKey] = useState(0);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;
  const errorRef = useRef(onError);
  errorRef.current = onError;

  useEffect(() => {
    let disposed = false;
    let retry: number | undefined;
    let raf = 0;
    const queue: StreamEvent[] = [];
    const flush = () => {
      raf = 0;
      const batch = queue.splice(0, queue.length);
      for (const event of batch) handlerRef.current(event);
    };
    const socket = new WebSocket(wsUrl());
    socket.onopen = () => setConnection("connected");
    socket.onclose = () => {
      setConnection("disconnected");
      if (!disposed) {
        retry = window.setTimeout(() => setReconnectKey((key) => key + 1), 2000);
      }
    };
    socket.onerror = () => socket.close();
    socket.onmessage = (event) => {
      let data: unknown;
      try {
        data = JSON.parse(event.data);
      } catch {
        errorRef.current("Received an invalid event from the API.");
        return;
      }
      const parsed = parseEvent(data);
      if (!parsed) return;
      queue.push(parsed);
      if (!raf) raf = window.requestAnimationFrame(flush);
    };
    return () => {
      disposed = true;
      window.clearTimeout(retry);
      window.cancelAnimationFrame(raf);
      socket.close();
    };
  }, [reconnectKey]);

  return { connection };
}
