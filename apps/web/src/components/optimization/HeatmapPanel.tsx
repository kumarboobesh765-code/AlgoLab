"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { loadSettings } from "@/lib/settings";
import { useToast } from "@/components/ui/Toast";

interface HeatmapCell {
  x: number;
  y: number;
  value: number | null;
  trades: number | null;
}

export interface HeatmapResponse {
  x_key: string;
  y_key: string;
  x_values: number[];
  y_values: number[];
  metric: string;
  cells: HeatmapCell[];
  best: HeatmapCell | null;
  worst: HeatmapCell | null;
}

const METRICS = ["sharpe_ratio", "net_pnl", "return_pct", "profit_factor", "win_rate"];

function parseValues(text: string): number[] | null {
  const vals = text
    .split(",")
    .map((s) => Number(s.trim()))
    .filter((n) => !Number.isNaN(n) && n !== 0 || n === 0);
  if (vals.length < 2 || vals.some((n) => Number.isNaN(n))) return null;
  return vals.slice(0, 25);
}

function cellColor(value: number | null, min: number, max: number): string {
  if (value === null) return "bg-slate-100 text-slate-300 dark:bg-slate-800";
  // Diverging scale: red (worst) → white → green (best)
  const span = max - min || 1;
  const t = (value - min) / span; // 0..1
  if (t >= 0.75) return "bg-green-500/80 text-white";
  if (t >= 0.55) return "bg-green-400/60 text-slate-900";
  if (t >= 0.45) return "bg-slate-200 text-slate-700 dark:bg-slate-600 dark:text-white";
  if (t >= 0.25) return "bg-red-400/60 text-slate-900";
  return "bg-red-500/80 text-white";
}

function fmtVal(v: number): string {
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
}

export function HeatmapPanel({
  strategyId,
  paramHints,
  start,
  end,
}: {
  strategyId: string;
  paramHints: string[];
  start: string;
  end: string;
}) {
  const { showToast } = useToast();
  const [xKey, setXKey] = useState("");
  const [xText, setXText] = useState("5, 10, 15, 20");
  const [yKey, setYKey] = useState("");
  const [yText, setYText] = useState("20, 30, 40");
  const [metric, setMetric] = useState("sharpe_ratio");
  const [result, setResult] = useState<HeatmapResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const keyOptions = paramHints.length > 0 ? paramHints : ["risk.stop_loss_pct", "risk.target_pct"];

  async function run() {
    setError(null);
    const xs = parseValues(xText);
    const ys = parseValues(yText);
    if (!xs || !ys) {
      setError("Enter at least 2 comma-separated numbers per axis (max 25 each).");
      return;
    }
    if (!strategyId) {
      setError("Pick a strategy first.");
      return;
    }
    setBusy(true);
    try {
      const s = loadSettings();
      const r = await api<HeatmapResponse>("/optimizations/heatmap", {
        method: "POST",
        body: JSON.stringify({
          strategy_id: strategyId,
          x_key: xKey || keyOptions[0],
          x_values: xs,
          y_key: yKey || (keyOptions[1] ?? keyOptions[0]),
          y_values: ys,
          metric,
          start,
          end,
          initial_capital: s.defaultCapital,
          costs_pct: s.costsPct,
        }),
      });
      setResult(r);
      showToast({ type: "success", title: "Heatmap ready", message: `${r.cells.length} combinations tested.` });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Heatmap failed");
    } finally {
      setBusy(false);
    }
  }

  // Lookup map for fast cell access
  const grid = new Map<string, HeatmapCell>();
  if (result) {
    for (const c of result.cells) grid.set(`${c.x}|${c.y}`, c);
  }
  const validValues = result ? result.cells.map((c) => c.value).filter((v): v is number => v !== null) : [];
  const minV = validValues.length ? Math.min(...validValues) : 0;
  const maxV = validValues.length ? Math.max(...validValues) : 1;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-400">X axis parameter</label>
          <select value={xKey} onChange={(e) => setXKey(e.target.value)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
            <option value="">Select…</option>
            {keyOptions.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <input value={xText} onChange={(e) => setXText(e.target.value)} placeholder="5, 10, 15, 20" className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs" />
        </div>
        <div>
          <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-400">Y axis parameter</label>
          <select value={yKey} onChange={(e) => setYKey(e.target.value)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
            <option value="">Select…</option>
            {keyOptions.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <input value={yText} onChange={(e) => setYText(e.target.value)} placeholder="20, 30, 40" className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs" />
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-400">Metric</label>
          <select value={metric} onChange={(e) => setMetric(e.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
            {METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <button
          onClick={run}
          disabled={busy}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
        >
          {busy ? "Testing…" : "Run heatmap"}
        </button>
        <span className="text-[11px] text-slate-400">Max 25×25 combos · runs on last 30 days of stored candles</span>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">{error}</p>
      )}

      {result && (
        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-0.5 text-[11px]">
            <thead>
              <tr>
                <th className="p-1.5 text-left font-medium text-slate-400">
                  {result.y_key.split(".").pop()} \ {result.x_key.split(".").pop()}
                </th>
                {result.x_values.map((x) => (
                  <th key={x} className="p-1.5 font-semibold text-slate-500">{fmtVal(x)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...result.y_values].reverse().map((y) => (
                <tr key={y}>
                  <th className="p-1.5 pr-2 text-right font-semibold text-slate-500">{fmtVal(y)}</th>
                  {result.x_values.map((x) => {
                    const c = grid.get(`${x}|${y}`);
                    const isBest = result.best && c && result.best.x === x && result.best.y === y;
                    return (
                      <td
                        key={x}
                        title={c?.value !== null && c?.value !== undefined ? `${result.metric}: ${c.value.toFixed(3)} · ${c.trades ?? 0} trades` : "backtest failed"}
                        className={`h-9 w-16 rounded text-center tabular-nums ${cellColor(c?.value ?? null, minV, maxV)} ${isBest ? "ring-2 ring-blue-600" : ""}`}
                      >
                        {c?.value !== null && c?.value !== undefined ? fmtVal(c.value) : "–"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {result.best && (
            <p className="mt-2 text-xs text-slate-500">
              Best <span className="font-mono text-slate-700">{result.metric}={fmtVal(result.best.value!)}</span> at{" "}
              <span className="font-mono text-slate-700">{result.best.x}</span> ×{" "}
              <span className="font-mono text-slate-700">{result.best.y}</span> — ringed blue above.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
