"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_URL, getToken, isMockMode } from "./api";

export interface StreamCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StreamTick {
  type: "tick";
  instrument_id: string;
  last_price: number;
  ts: string;
  candle: StreamCandle;
}

interface ControlFrame {
  type: string;
  message?: string;
  provider?: string;
  is_demo?: boolean;
  supports_streaming?: boolean;
}

export interface StreamState {
  connected: boolean;
  /** Latest tick per instrument, keyed by symbol. */
  ticks: Record<string, StreamTick>;
  provider: string | null;
  isDemo: boolean | null;
  supportsStreaming: boolean | null;
  error: string | null;
}

/** Frames arrive faster than React should re-render; coalesce them per frame budget. */
const BATCH_MS = 250;

/**
 * Subscribe to the market WebSocket for `symbols` at `interval`.
 *
 * Ticks are buffered and flushed on an interval so a fast feed does not force a
 * re-render per tick. The socket is reference-counted by nothing: each hook owns
 * its own connection, and changing symbols re-subscribes on the same socket
 * rather than reconnecting, which avoids a visible gap on every symbol change.
 *
 * Mock mode short-circuits to a local interval timer so the streaming UI is
 * demonstrable with no backend running.
 */
export function useMarketStream(symbols: string[], interval = "1m"): StreamState {
  const [state, setState] = useState<StreamState>({
    connected: false,
    ticks: {},
    provider: null,
    isDemo: null,
    supportsStreaming: null,
    error: null,
  });

  const buffer = useRef<Record<string, StreamTick>>({});
  const socketRef = useRef<WebSocket | null>(null);
  // Mock mode is a session-level setting (env default + localStorage override),
// so resolve it once during initialisation rather than inside the effect body.
const [mockMode] = useState(() => isMockMode());

  const flush = useCallback(() => {
    const pending = buffer.current;
    buffer.current = {};
    if (Object.keys(pending).length === 0) return;
    setState((prev) => ({ ...prev, ticks: { ...prev.ticks, ...pending } }));
  }, []);

  const key = symbols.join(",");

  useEffect(() => {
    const wanted = key.split(",").filter(Boolean);
    if (wanted.length === 0) return;

    if (mockMode) {
      // Ticks flow through the same buffer and batched flush as a real socket.
      const timer = setInterval(() => {
        const now = Math.floor(Date.now() / 1000);
        const bar = Math.floor(now / 300) * 300;
        for (const symbol of wanted) {
          const prev = buffer.current[symbol]?.candle;
          const base = prev?.close ?? 22000 + Math.sin(now / 60) * 120;
          const close = base + Math.sin(now / 7 + symbol.length) * 4;
          buffer.current[symbol] = {
            type: "tick",
            instrument_id: symbol,
            last_price: close,
            ts: new Date().toISOString(),
            candle: {
              time: bar,
              open: prev?.open ?? close,
              high: Math.max(prev?.high ?? close, close),
              low: Math.min(prev?.low ?? close, close),
              close,
              volume: (prev?.volume ?? 0) + 900,
            },
          };
        }
      }, 1000);
      const batcher = setInterval(flush, BATCH_MS);
      return () => {
        clearInterval(timer);
        clearInterval(batcher);
      };
    }

    const token = getToken();
    // Browsers cannot set headers on a WebSocket, so the token goes in the
    // query string; the server also accepts an Authorization header for
    // non-browser clients.
    const wsUrl =
      API_URL.replace(/^http/, "ws") +
      "/api/v1/ws/market" +
      (token ? `?token=${encodeURIComponent(token)}` : "");
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setState((prev) => ({ ...prev, connected: true, error: null }));
      ws.send(
        JSON.stringify({
          action: "subscribe",
          symbols: wanted,
          interval,
        }),
      );
    };

    ws.onmessage = (event) => {
      let frame: StreamTick | ControlFrame;
      try {
        frame = JSON.parse(event.data as string);
      } catch {
        return;
      }
      if (frame.type === "tick") {
        buffer.current[(frame as StreamTick).instrument_id] = frame as StreamTick;
        return;
      }
      const control = frame as ControlFrame;
      setState((prev) => ({
        ...prev,
        provider: control.provider ?? prev.provider,
        isDemo: control.is_demo ?? prev.isDemo,
        supportsStreaming: control.supports_streaming ?? prev.supportsStreaming,
        error: control.type === "error" ? (control.message ?? "stream error") : prev.error,
      }));
    };

    ws.onerror = () => {
      setState((prev) => ({ ...prev, connected: false, error: "stream connection failed" }));
    };

    ws.onclose = () => {
      setState((prev) => ({ ...prev, connected: false }));
    };

    const batcher = setInterval(flush, BATCH_MS);

    return () => {
      clearInterval(batcher);
      socketRef.current = null;
      ws.onclose = null;
      ws.close();
    };
    // `key` collapses the symbol array to a stable primitive dependency.
  }, [key, interval, flush, mockMode]);

  return useMemo(
    () =>
      mockMode
        ? {
            connected: true,
            ticks: state.ticks,
            provider: "mock",
            isDemo: true,
            supportsStreaming: true,
            error: null,
          }
        : state,
    [mockMode, state],
  );
}