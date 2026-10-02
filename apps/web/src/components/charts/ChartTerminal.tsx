"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import {
  api,
  type ChartCandle,
  type IndicatorCatalogEntry,
  type QuantCatalog,
  type QuantSeriesResponse,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

/**
 * Charting terminal: candlesticks + volume pane + indicator overlay panes.
 *
 * Data comes from a single `GET /quant/series` call so price bars and every
 * indicator series share one index and cannot drift out of alignment.
 * lightweight-charts is driven imperatively (not JSX) because the library owns
 * its own DOM tree; React only manages the container and the controls.
 */

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d"] as const;

/** Overlay families and where they draw. Price-scale overlays stay on pane 0;
 *  oscillators (bounded, unrelated units) get their own pane. */
const OSCILLATOR_TYPES = new Set([
  "RSI", "MACD", "STOCH", "ADX", "WILLR", "MFI", "TRIX", "TSI", "ULTOSC",
  "CMO", "PPO", "AO", "AROON", "DPO", "STOCHRSI", "HV", "NATR",
]);
const BAND_TYPES = new Set(["BBANDS", "DONCHIAN", "KC"]);
const CUMULATIVE_TYPES = new Set(["OBV", "AD", "PVT", "NVI"]);

const PALETTE = [
  "#2563eb", "#f59e0b", "#10b981", "#8b5cf6", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
];

interface Overlay {
  id: string;
  type: string;
  params: Record<string, number | string>;
}

function buildToken(o: Overlay): string {
  const entries = Object.entries(o.params);
  if (entries.length === 0) return o.type;
  const first = entries[0];
  const rest = entries.slice(1);
  const key = first[0];
  const val = first[1];
  // single numeric "length"-ish param reads better positionally
  if (rest.length === 0 && typeof val === "number" && key === "length") {
    return `${o.type}:${val}`;
  }
  return `${o.type}:${entries.map(([k, v]) => `${k}=${v}`).join(",")}`;
}

function shortLabel(token: string): string {
  return token.replace(/length=/g, "").replace(/:(\d+)/, " $1");
}

export default function ChartTerminalPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const overlayRef = useRef<ISeriesApi<"Line">[]>([]);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const [symbol, setSymbol] = useState("NIFTY");
  const [interval, setInterval] = useState<string>("5m");
  const [bars, setBars] = useState(500);
  const [catalog, setCatalog] = useState<IndicatorCatalogEntry[]>([]);
  const [overlays, setOverlays] = useState<Overlay[]>([
    { id: "o1", type: "SMA", params: { length: 20 } },
  ]);
  const [data, setData] = useState<QuantSeriesResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<ChartCandle | null>(null);
  const [showVolume, setShowVolume] = useState(true);
  const [picker, setPicker] = useState("");

  const tokens = useMemo(
    () => overlays.map(buildToken).filter(Boolean),
    [overlays],
  );

  // ---- chart lifecycle -------------------------------------------------
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#ffffff" },
        textColor: "#475569",
        panes: { separatorColor: "#e2e8f0", separatorHoverColor: "#cbd5e1" },
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "#f1f5f9" },
        horzLines: { color: "#f1f5f9" },
      },
      rightPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false },
      crosshair: {
        mode: 0,
        vertLine: { color: "#94a3b8", labelBackgroundColor: "#475569" },
        horzLine: { color: "#94a3b8", labelBackgroundColor: "#475569" },
      },
      autoSize: true,
      localization: {
        priceFormatter: (p: number) =>
          p >= 10000 ? p.toLocaleString("en-IN") : p.toFixed(2),
      },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderUpColor: "#16a34a",
      borderDownColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
      priceLineVisible: true,
    });
    chartRef.current = chart;
    candlesRef.current = candles;
    volRef.current = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" } }, 1);

    return () => {
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      volRef.current = null;
    };
  }, []);

  // ---- data -----------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    api<QuantCatalog>("/quant/catalog")
      .then((c) => {
        if (!cancelled) setCatalog(c.indicators);
      })
      .catch(() => {
        /* catalog is only used to populate the picker */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchSeries = useCallback(async (): Promise<QuantSeriesResponse> => {
    const qs = new URLSearchParams({
      symbol,
      interval,
      bars: String(bars),
      indicators: tokens.join(","),
    });
    return api<QuantSeriesResponse>(`/quant/series?${qs}`);
  }, [symbol, interval, bars, tokens]);

  // Silent reload whenever inputs change. No `setState` in the effect body --
  // results land in the promise callbacks, which avoids cascading renders.
  useEffect(() => {
    let cancelled = false;
    fetchSeries()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load chart data");
      });
    return () => {
      cancelled = true;
    };
  }, [fetchSeries]);

  // Explicit refresh is user-initiated, so it may own the busy flag.
  const refresh = async () => {
    setBusy(true);
    try {
      setData(await fetchSeries());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load chart data");
    } finally {
      setBusy(false);
    }
  };

  // ---- render into the chart -----------------------------------------
  useEffect(() => {
    const chart = chartRef.current;
    const c = candlesRef.current;
    if (!chart || !c || !data) return;

    const barsIn = data.candles.map((b) => ({
      time: b.time as Time,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    c.setData(barsIn);

    if (volRef.current) {
      volRef.current.setData(
        data.candles.map((b) => ({
          time: b.time as Time,
          value: b.volume,
          color: b.close >= b.open ? "#16a34a55" : "#dc262655",
        })),
      );
      volRef.current.applyOptions({ visible: showVolume });
    }

    // tear down previous overlay lines
    for (const s of overlayRef.current) {
      try {
        chart.removeSeries(s);
      } catch {
        /* already gone */
      }
    }
    overlayRef.current = [];

    let paneIndex = 2;
    const entries = Object.entries(data.series);
    entries.forEach(([token, outputs], i) => {
      const color = PALETTE[i % PALETTE.length];
      const type = token.split(":")[0].toUpperCase();
      const oscPane = OSCILLATOR_TYPES.has(type);
      const pane = oscPane ? paneIndex++ : 0;
      const target = BAND_TYPES.has(type) || CUMULATIVE_TYPES.has(type) ? "HistogramSeries" : "LineSeries";

      for (const [outName, values] of Object.entries(outputs)) {
        const points = values
          .map((v, idx) =>
            v === null ? null : { time: data.candles[idx].time as Time, value: v },
          )
          .filter((p): p is { time: Time; value: number } => p !== null);

        if (target === "HistogramSeries") continue; // bands drawn as lines below
        const s = chart.addSeries(
          LineSeries,
          {
            color,
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: true,
            title: `${shortLabel(token)}${Object.keys(outputs).length > 1 ? ` ${outName}` : ""}`,
          },
          pane,
        );
        s.setData(points);
        overlayRef.current.push(s);
      }

      // bands: upper/middle/lower with a light fill between
      if (BAND_TYPES.has(type)) {
        const keys = Object.keys(outputs);
        const pick = (k: string) =>
          outputs[k]
            .map((v, idx) =>
              v === null ? null : { time: data.candles[idx].time as Time, value: v },
            )
            .filter((p): p is { time: Time; value: number } => p !== null);
        const upperKey = keys.find((k) => k.toLowerCase().startsWith("up")) ?? keys[0];
        const lowerKey = keys.find((k) => k.toLowerCase().startsWith("low")) ?? keys[keys.length - 1];
        const midKey = keys.find((k) => k.toLowerCase().startsWith("mid"));

        const base = {
          lineWidth: 1 as const,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        };
        const u = chart.addSeries(LineSeries, { ...base, color, title: `${shortLabel(token)} upper` }, 0);
        u.setData(pick(upperKey));
        overlayRef.current.push(u);
        const l = chart.addSeries(LineSeries, { ...base, color, title: `${shortLabel(token)} lower` }, 0);
        l.setData(pick(lowerKey));
        overlayRef.current.push(l);
        if (midKey) {
          const m = chart.addSeries(
            LineSeries,
            { ...base, color, lineStyle: 2, title: `${shortLabel(token)} mid` },
            0,
          );
          m.setData(pick(midKey));
          overlayRef.current.push(m);
        }
      }
    });

    chart.timeScale().fitContent();
  }, [data, showVolume]);

  // ---- crosshair readout ---------------------------------------------
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;
    const byTime = new Map(data.candles.map((b) => [b.time, b]));
    const handler = (param: { time?: unknown }) => {
      const t = Number(param.time);
      if (!Number.isFinite(t)) {
        setHover(null);
        return;
      }
      setHover(byTime.get(t) ?? null);
    };
    chart.subscribeCrosshairMove(handler);
    return () => chart.unsubscribeCrosshairMove(handler);
  }, [data]);

  // ---- controls -------------------------------------------------------
  function addOverlay(type: string) {
    const spec = catalog.find((c) => c.type === type);
    const params: Record<string, number | string> = {};
    if (spec) {
      for (const [name, pspec] of Object.entries(spec.params)) {
        if (pspec.kind === "int" || pspec.kind === "float") {
          params[name] = pspec.default as number;
        } else {
          params[name] = pspec.default as string;
        }
      }
    }
    setOverlays((prev) => [...prev, { id: `o${Date.now()}`, type, params }]);
    setPicker("");
  }

  function setParam(id: string, key: string, value: number | string) {
    setOverlays((prev) =>
      prev.map((o) => (o.id === id ? { ...o, params: { ...o.params, [key]: value } } : o)),
    );
  }

  const last = data?.candles.at(-1);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-[11px] font-medium text-slate-500">Symbol</label>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-32 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] font-medium text-slate-500">Timeframe</label>
          <select
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            {TIMEFRAMES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-[11px] font-medium text-slate-500">Bars</label>
          <select
            value={bars}
            onChange={(e) => setBars(Number(e.target.value))}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            {[200, 500, 1000, 2000].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={refresh}
          disabled={busy}
          className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {busy ? "Loading…" : "Refresh"}
        </button>
        <label className="flex items-center gap-1.5 pb-1.5 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={showVolume}
            onChange={(e) => setShowVolume(e.target.checked)}
          />
          Volume
        </label>
        {data?.is_demo && <Badge tone="amber">demo data</Badge>}
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}

      {Object.keys(data?.errors ?? {}).length > 0 && (
        <div className="rounded-md bg-amber-50 px-3 py-2 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-200">
          {Object.entries(data!.errors).map(([token, msg]) => (
            <p key={token}>
              <span className="font-semibold">{token}</span>: {msg}
            </p>
          ))}
        </div>
      )}

      <Card
        title={`${data?.symbol ?? symbol} · ${interval}`}
        subtitle={
          hover
            ? `O ${hover.open.toFixed(2)}  H ${hover.high.toFixed(2)}  L ${hover.low.toFixed(2)}  C ${hover.close.toFixed(2)}  Vol ${Math.round(hover.volume).toLocaleString("en-IN")}`
            : last
              ? `O ${last.open.toFixed(2)}  H ${last.high.toFixed(2)}  L ${last.low.toFixed(2)}  C ${last.close.toFixed(2)}  Vol ${Math.round(last.volume).toLocaleString("en-IN")}`
              : "loading…"
        }
      >
        <div ref={containerRef} className="h-[560px] w-full" />
      </Card>

      <Card title="Indicators" subtitle="Price-scale overlays draw on the candles; oscillators get their own pane">
        <div className="flex flex-wrap gap-2">
          <select
            value={picker}
            onChange={(e) => setPicker(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">Add indicator…</option>
            {catalog.map((c) => (
              <option key={c.type} value={c.type}>
                {c.type}
              </option>
            ))}
          </select>
          <button
            onClick={() => picker && addOverlay(picker)}
            disabled={!picker}
            className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40"
          >
            Add
          </button>
        </div>

        {overlays.length === 0 && (
          <p className="mt-3 text-xs text-slate-400">No indicators yet.</p>
        )}

        <div className="mt-3 space-y-2">
          {overlays.map((o, i) => {
            const spec = catalog.find((c) => c.type === o.type);
            const color = PALETTE[i % PALETTE.length];
            return (
              <div
                key={o.id}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 px-3 py-2"
              >
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: color }} />
                <span className="text-xs font-semibold text-slate-700">{o.type}</span>
                {spec &&
                  Object.entries(spec.params).map(([name, pspec]) => (
                    <label key={name} className="flex items-center gap-1 text-[11px] text-slate-500">
                      {name}
                      {pspec.kind === "str" ? (
                        <select
                          value={String(o.params[name] ?? pspec.default)}
                          onChange={(e) => setParam(o.id, name, e.target.value)}
                          className="rounded border border-slate-300 px-1 py-0.5 text-[11px]"
                        >
                          {pspec.choices?.map((ch) => (
                            <option key={ch} value={ch}>
                              {ch}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="number"
                          value={Number(o.params[name] ?? pspec.default)}
                          min={pspec.ge}
                          max={pspec.le}
                          step={pspec.kind === "int" ? 1 : 0.1}
                          onChange={(e) => setParam(o.id, name, Number(e.target.value))}
                          className="w-20 rounded border border-slate-300 px-1 py-0.5 text-[11px]"
                        />
                      )}
                    </label>
                  ))}
                <button
                  onClick={() => setOverlays((prev) => prev.filter((x) => x.id !== o.id))}
                  className="ml-auto rounded px-2 py-0.5 text-[11px] text-red-600 hover:bg-red-50"
                >
                  Remove
                </button>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}