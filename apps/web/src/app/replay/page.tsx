"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  type BacktestRun,
  type ReplayCandle,
  type Strategy,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

const SPEEDS = [
  { label: "1x", ms: 400 },
  { label: "2x", ms: 200 },
  { label: "4x", ms: 100 },
  { label: "8x", ms: 50 },
];

const WINDOW = 120;

function fmtMoney(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function fmtTime(t: string): string {
  return t.slice(0, 16).replace("T", " ");
}

interface IndexedTrade {
  entryIdx: number;
  exitIdx: number;
  direction: "long" | "short";
  quantity: number;
  entryPrice: number;
  exitPrice: number;
  exitReason: string;
  pnl: number;
}

function timeKey(t: string): string {
  return t.slice(0, 16);
}

export default function ReplayPage() {
  const { user, loading: authLoading } = useAuth();
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [candles, setCandles] = useState<ReplayCandle[]>([]);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState(200);
  const [error, setError] = useState<string | null>(null);

  const idxRef = useRef(0);

  useEffect(() => {
    idxRef.current = idx;
  }, [idx]);

  useEffect(() => {
    if (!user) return;
    const wanted = new URLSearchParams(window.location.search).get("run");
    api<BacktestRun[]>("/backtests")
      .then((all) => {
        const done = all.filter((r) => r.status === "completed" && r.result_summary);
        setRuns(done);
        if (done.length > 0 && wanted && done.some((r) => r.id === wanted)) {
          setRunId(wanted);
        }
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load backtests"),
      );
    api<Strategy[]>("/strategies")
      .then(setStrategies)
      .catch(() => {});
  }, [user]);

  useEffect(() => {
    if (!user || !runId) return;
    let cancelled = false;
    Promise.all([
      api<BacktestRun>(`/backtests/${runId}`),
      api<ReplayCandle[]>(`/backtests/${runId}/candles`),
    ])
      .then(([detail, cs]) => {
        if (cancelled) return;
        setRun(detail);
        setCandles(cs);
        setIdx(0);
        idxRef.current = 0;
        setPlaying(false);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load replay data");
      });
    return () => {
      cancelled = true;
    };
  }, [user, runId]);

  useEffect(() => {
    if (!playing || candles.length === 0) return;
    const iv = setInterval(() => {
      const next = idxRef.current + 1;
      if (next >= candles.length - 1) {
        idxRef.current = candles.length - 1;
        setIdx(candles.length - 1);
        setPlaying(false);
      } else {
        idxRef.current = next;
        setIdx(next);
      }
    }, speedMs);
    return () => clearInterval(iv);
  }, [playing, speedMs, candles.length]);

  const trades: IndexedTrade[] = useMemo(() => {
    if (!run?.result_summary || candles.length === 0) return [];
    const index = new Map<string, number>();
    candles.forEach((c, i) => index.set(timeKey(c.timestamp), i));
    const out: IndexedTrade[] = [];
    for (const t of run.result_summary.trades) {
      out.push({
        entryIdx: index.get(timeKey(t.entry_time)) ?? -1,
        exitIdx: index.get(timeKey(t.exit_time)) ?? -1,
        direction: t.direction,
        quantity: t.quantity,
        entryPrice: t.entry_price,
        exitPrice: t.exit_price,
        exitReason: t.exit_reason,
        pnl: t.pnl,
      });
    }
    return out.sort((a, b) => a.entryIdx - b.entryIdx);
  }, [run, candles]);

  const equityCurve = run?.result_summary?.equity_curve ?? [];
  const maxIdx = Math.max(
    0,
    Math.min(candles.length, equityCurve.length) - 1,
  );
  const clampedIdx = Math.min(idx, maxIdx);

  const openTrade = useMemo(
    () =>
      trades.find(
        (t) => t.entryIdx >= 0 && t.entryIdx <= clampedIdx && (t.exitIdx < 0 || t.exitIdx > clampedIdx),
      ) ?? null,
    [trades, clampedIdx],
  );

  const closedTrades = useMemo(
    () => trades.filter((t) => t.exitIdx >= 0 && t.exitIdx <= clampedIdx),
    [trades, clampedIdx],
  );

  const realizedPnl = useMemo(
    () => closedTrades.reduce((sum, t) => sum + t.pnl, 0),
    [closedTrades],
  );

  const lastEvent = useMemo(() => {
    let label = "—";
    for (const t of trades) {
      if (t.entryIdx === clampedIdx) label = `Entry ${t.direction} @ ${t.entryPrice}`;
      else if (t.exitIdx === clampedIdx)
        label = `Exit (${t.exitReason}) P&L ${t.pnl >= 0 ? "+" : ""}${fmtMoney(t.pnl)}`;
    }
    return label;
  }, [trades, clampedIdx]);

  const candle = candles[clampedIdx];
  const equityPoint = equityCurve[clampedIdx];
  const strategyName =
    strategies.find((s) => s.id === run?.strategy_id)?.name ?? run?.strategy_id;

  const chart = useMemo(() => {
    if (!candle) return null;
    const start = Math.max(0, clampedIdx - WINDOW + 1);
    const view = candles.slice(start, clampedIdx + 1);
    const w = 760;
    const h = 260;
    const padL = 4;
    const padR = 56;
    const padY = 10;
    const lows = view.map((c) => c.low);
    const highs = view.map((c) => c.high);
    if (openTrade) {
      highs.push(openTrade.entryPrice);
      lows.push(openTrade.entryPrice);
    }
    const min = Math.min(...lows);
    const max = Math.max(...highs);
    const span = max - min || 1;
    const slot = (w - padL - padR) / Math.max(view.length, 1);
    const x = (i: number) => padL + i * slot + slot / 2;
    const y = (v: number) => padY + (1 - (v - min) / span) * (h - 2 * padY);
    const bw = Math.max(1.5, slot * 0.6);
    return { start, view, w, h, padL, padR, slot, x, y, bw, min, max };
  }, [candle, candles, clampedIdx, openTrade]);

  function step(delta: number) {
    setPlaying(false);
    setIdx((cur) => Math.min(Math.max(cur + delta, 0), maxIdx));
  }

  function jumpToEvent(dir: 1 | -1) {
    setPlaying(false);
    const boundaries = trades.flatMap((t) =>
      [t.entryIdx, t.exitIdx].filter((i) => i >= 0),
    );
    const target =
      dir === 1
        ? boundaries.find((b) => b > clampedIdx)
        : [...boundaries].reverse().find((b) => b < clampedIdx);
    if (target !== undefined) setIdx(target);
  }

  if (!authLoading && !user) {
    return (
      <Card>
        <div className="py-10 text-center">
          <p className="text-sm text-slate-500">Sign in to replay backtests.</p>
          <Link
            href="/login"
            className="mt-4 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Sign in
          </Link>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card
        title="Trade replay"
        subtitle="Step bar-by-bar through a completed backtest — exactly as the engine saw it."
        actions={
          <select
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            className="w-72 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          >
            <option value="">
              {runs.length === 0
                ? "No completed backtest runs"
                : `${runs.length} completed runs`}
            </option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {fmtTime(r.config?.start ?? "")} → {fmtTime(r.config?.end ?? "")} ·{" "}
                {r.version_number}
              </option>
            ))}
          </select>
        }
      >
        {runs.length === 0 ? (
          <p className="text-xs text-slate-500">
            Run a backtest first —{" "}
            <Link href="/backtest" className="text-sky-600 hover:underline">
              go to Backtest →
            </Link>
          </p>
        ) : !candle ? (
          <p className="text-xs text-slate-500">Select a run and wait for data…</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => {
                  setPlaying(false);
                  setIdx(0);
                }}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                ⏮ Reset
              </button>
              <button
                onClick={() => jumpToEvent(-1)}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                ◀◀ Event
              </button>
              <button
                onClick={() => step(-1)}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                ◀ Bar
              </button>
              <button
                onClick={() =>
                  clampedIdx >= maxIdx
                    ? (setIdx(0), setPlaying(true))
                    : setPlaying(!playing)
                }
                className="rounded-md bg-sky-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-sky-700"
              >
                {playing ? "⏸ Pause" : "▶ Play"}
              </button>
              <button
                onClick={() => step(1)}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                Bar ▶
              </button>
              <button
                onClick={() => jumpToEvent(1)}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                Event ▶▶
              </button>
              <select
                value={speedMs}
                onChange={(e) => setSpeedMs(Number(e.target.value))}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-xs text-slate-800"
              >
                {SPEEDS.map((s) => (
                  <option key={s.ms} value={s.ms}>
                    {s.label}
                  </option>
                ))}
              </select>
              <span className="ml-auto tabular-nums text-xs text-slate-500">
                bar {clampedIdx + 1} / {maxIdx + 1}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={maxIdx}
              value={clampedIdx}
              onChange={(e) => {
                setPlaying(false);
                setIdx(Number(e.target.value));
              }}
              className="mt-3 w-full accent-sky-600"
            />
          </>
        )}
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </Card>

      {run && candle && chart && equityPoint && (
        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <Card
            title={`${run.config?.symbol ?? "?"} · ${run.config?.timeframe ?? "?"}`}
            subtitle={`Strategy: ${strategyName ?? "?"} · v${run.version_number}`}
            actions={
              <Badge tone={openTrade ? (openTrade.direction === "long" ? "green" : "red") : "slate"}>
                {openTrade ? `IN ${openTrade.direction.toUpperCase()}` : "FLAT"}
              </Badge>
            }
          >
            <svg
              viewBox={`0 0 ${chart.w} ${chart.h}`}
              className="w-full"
              role="img"
              aria-label="Replay candlestick chart"
            >
              {chart.view.map((c, i) => {
                const gi = chart.start + i;
                const up = c.close >= c.open;
                const color = up ? "#059669" : "#dc2626";
                const cx = chart.x(i);
                const bodyTop = chart.y(Math.max(c.open, c.close));
                const bodyBot = chart.y(Math.min(c.open, c.close));
                const isCurrent = gi === clampedIdx;
                return (
                  <g key={gi} opacity={isCurrent ? 1 : 0.85}>
                    {isCurrent && (
                      <rect
                        x={cx - chart.slot / 2}
                        y={0}
                        width={chart.slot}
                        height={chart.h}
                        fill="#e0f2fe"
                      />
                    )}
                    <line
                      x1={cx}
                      x2={cx}
                      y1={chart.y(c.high)}
                      y2={chart.y(c.low)}
                      stroke={color}
                      strokeWidth="1"
                    />
                    <rect
                      x={cx - chart.bw / 2}
                      y={bodyTop}
                      width={chart.bw}
                      height={Math.max(1, bodyBot - bodyTop)}
                      fill={color}
                    />
                  </g>
                );
              })}
              {openTrade && openTrade.entryIdx >= chart.start && (
                <line
                  x1={0}
                  x2={chart.w}
                  y1={chart.y(openTrade.entryPrice)}
                  y2={chart.y(openTrade.entryPrice)}
                  stroke="#f59e0b"
                  strokeDasharray="5 4"
                  strokeWidth="1.2"
                />
              )}
              {trades.map((t, ti) =>
                [t.entryIdx, t.exitIdx].map((bi, kind) => {
                  if (bi < chart.start || bi > clampedIdx) return null;
                  const cx = chart.x(bi - chart.start);
                  const isEntry = kind === 0;
                  const price = isEntry ? t.entryPrice : t.exitPrice;
                  const py = isEntry
                    ? chart.y(price) + 14
                    : chart.y(price) - 14;
                  const tri = isEntry
                    ? `M${cx},${py - 8} l-5,9 l10,0 z`
                    : `M${cx},${py + 8} l-5,-9 l10,0 z`;
                  return (
                    <g key={`${ti}-${kind}`}>
                      <path d={tri} fill={isEntry ? "#059669" : "#dc2626"} />
                      <text
                        x={cx}
                        y={isEntry ? py + 18 : py - 12}
                        textAnchor="middle"
                        fontSize="9"
                        fill={isEntry ? "#059669" : "#dc2626"}
                        fontWeight="bold"
                      >
                        {isEntry ? "B" : "S"}
                      </text>
                    </g>
                  );
                }),
              )}
              <text
                x={chart.w - chart.padR + 6}
                y={14}
                fontSize="10"
                fill="#64748b"
                fontFamily="monospace"
              >
                {candle.close.toFixed(1)}
              </text>
              <line
                x1={chart.x(chart.view.length - 1)}
                x2={chart.w - chart.padR}
                y1={chart.y(candle.close)}
                y2={chart.y(candle.close)}
                stroke="#94a3b8"
                strokeWidth="0.8"
              />
            </svg>

            <h3 className="mt-3 mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Equity ({fmtMoney(equityCurve[0]?.equity ?? 0)} → {fmtMoney(equityPoint.equity)})
            </h3>
            <svg viewBox="0 0 760 70" className="w-full" role="img" aria-label="Equity so far">
              {(() => {
                const pts = equityCurve.slice(0, clampedIdx + 1);
                if (pts.length < 2) return null;
                const vals = pts.map((p) => p.equity);
                const mn = Math.min(...vals);
                const mx = Math.max(...vals);
                const span = mx - mn || 1;
                const path = pts
                  .map(
                    (p, i) =>
                      `${i === 0 ? "M" : "L"}${((i / (pts.length - 1)) * 752 + 4).toFixed(1)},${(62 - ((p.equity - mn) / span) * 54).toFixed(1)}`,
                  )
                  .join(" ");
                return (
                  <path
                    d={path}
                    fill="none"
                    stroke={equityPoint.equity >= (equityCurve[0]?.equity ?? 0) ? "#059669" : "#dc2626"}
                    strokeWidth="1.6"
                  />
                );
              })()}
            </svg>
          </Card>

          <div className="space-y-4">
            <Card title="Bar">
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs tabular-nums">
                <dt className="col-span-2 mb-1 font-medium text-slate-700">
                  {fmtTime(candle.timestamp)}
                </dt>
                <dt className="text-slate-400">Open</dt>
                <dd>{candle.open}</dd>
                <dt className="text-slate-400">High</dt>
                <dd className="text-emerald-600">{candle.high}</dd>
                <dt className="text-slate-400">Low</dt>
                <dd className="text-red-600">{candle.low}</dd>
                <dt className="text-slate-400">Close</dt>
                <dd className="font-semibold">{candle.close}</dd>
                <dt className="text-slate-400">Volume</dt>
                <dd>{candle.volume.toLocaleString("en-IN")}</dd>
                <dt className="mt-1 text-slate-400">Equity</dt>
                <dd className="mt-1 font-semibold">{fmtMoney(equityPoint.equity)}</dd>
                <dt className="text-slate-400">Realized P&L</dt>
                <dd
                  className={
                    realizedPnl >= 0
                      ? "text-emerald-600"
                      : "text-red-600"
                  }
                >
                  {realizedPnl >= 0 ? "+" : ""}
                  {fmtMoney(realizedPnl)}
                </dd>
                <dt className="col-span-2 mt-1 text-slate-400">Last event</dt>
                <dd className="col-span-2 font-medium text-slate-700">{lastEvent}</dd>
              </dl>
            </Card>

            <Card title="Position">
              {!openTrade ? (
                <p className="text-xs text-slate-500">
                  Flat — no open position at this bar.
                </p>
              ) : (
                (() => {
                  const unreal =
                    openTrade.direction === "long"
                      ? (candle.close - openTrade.entryPrice) * openTrade.quantity
                      : (openTrade.entryPrice - candle.close) * openTrade.quantity;
                  return (
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs tabular-nums">
                      <dt className="text-slate-400">Side</dt>
                      <dd>
                        <Badge tone={openTrade.direction === "long" ? "green" : "red"}>
                          {openTrade.direction}
                        </Badge>
                      </dd>
                      <dt className="text-slate-400">Qty</dt>
                      <dd>{openTrade.quantity}</dd>
                      <dt className="text-slate-400">Entry</dt>
                      <dd>{openTrade.entryPrice}</dd>
                      <dt className="text-slate-400">Unrealized</dt>
                      <dd
                        className={`font-semibold ${
                          unreal >= 0 ? "text-emerald-600" : "text-red-600"
                        }`}
                      >
                        {unreal >= 0 ? "+" : ""}
                        {fmtMoney(unreal)}
                      </dd>
                    </dl>
                  );
                })()
              )}
            </Card>

            <Card title={`Closed trades (${closedTrades.length}/${trades.length})`}>
              {closedTrades.length === 0 ? (
                <p className="text-xs text-slate-500">No closed trades yet.</p>
              ) : (
                <ul className="divide-y divide-slate-100 text-xs">
                  {[...closedTrades].reverse().slice(0, 6).map((t, i) => (
                    <li key={i} className="flex items-center justify-between gap-2 py-1.5">
                      <span className="text-slate-500">
                        {t.direction} ×{t.quantity} @ {t.entryPrice} → {t.exitPrice}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <Badge tone={t.pnl >= 0 ? "green" : "red"}>
                          {t.pnl >= 0 ? "+" : ""}
                          {fmtMoney(t.pnl)}
                        </Badge>
                        <Badge tone={t.exitReason === "target" ? "green" : t.exitReason === "stop_loss" ? "red" : "amber"}>
                          {t.exitReason}
                        </Badge>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
