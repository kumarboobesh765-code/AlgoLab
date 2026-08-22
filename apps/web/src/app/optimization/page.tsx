"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type OptimizationCreate,
  type OptimizationResult,
  type OptimizationRun,
  type Strategy,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

function todayISO(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const METRICS = [
  "sharpe_ratio",
  "net_pnl",
  "return_pct",
  "profit_factor",
  "win_rate",
  "max_drawdown_pct",
];

function fmt(v: number | null): string {
  if (v === null || v === undefined) return "-";
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export default function OptimizationPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [runs, setRuns] = useState<OptimizationRun[]>([]);
  const [selected, setSelected] = useState<OptimizationRun | null>(null);
  const [results, setResults] = useState<OptimizationResult[]>([]);

  // Form state
  const [strategyId, setStrategyId] = useState("");
  const [method, setMethod] = useState<"grid" | "walk_forward">("grid");
  const [start, setStart] = useState(todayISO(-30));
  const [end, setEnd] = useState(todayISO(-1));
  const [targetMetric, setTargetMetric] = useState("sharpe_ratio");
  const [paramRangesText, setParamRangesText] = useState(
    '{\n  "indicators.f.params.length": [5, 10, 15, 20, 25, 30],\n  "indicators.s.params.length": [20, 30, 40, 50]\n}'
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api<Strategy[]>("/strategies").then((all) => {
      const usable = all.filter((s) => s.definition !== null);
      setStrategies(usable);
      if (usable.length > 0) setStrategyId((cur) => cur || usable[0].id);
    }).catch(() => {});
    api<OptimizationRun[]>("/optimizations").then(setRuns).catch(() => {});
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function runOptimization() {
    if (!strategyId) return;
    let paramRanges: Record<string, number[]>;
    try {
      paramRanges = JSON.parse(paramRangesText);
    } catch {
      setError("Invalid JSON in parameter ranges");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const payload: OptimizationCreate = {
        strategy_id: strategyId,
        method,
        param_ranges: paramRanges,
        start,
        end,
        target_metric: targetMetric,
      };
      const run = await api<OptimizationRun>("/optimizations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setRuns([run, ...runs]);
      setSelected(run);
      if (run.status === "completed") {
        const res = await api<OptimizationResult[]>(`/optimizations/${run.id}/results`);
        setResults(res);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Optimization failed");
    } finally {
      setRunning(false);
    }
  }

  async function loadRun(id: string) {
    try {
      const run = await api<OptimizationRun>(`/optimizations/${id}`);
      setSelected(run);
      if (run.status === "completed") {
        const res = await api<OptimizationResult[]>(`/optimizations/${id}/results`);
        setResults(res);
      }
    } catch { /* ignore */ }
  }

  const completed = runs.filter((r) => r.status === "completed");

  return (
    <div className="space-y-4">
      <Card title="Optimization" subtitle="Grid search or walk-forward analysis over parameter ranges.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-xs font-medium text-slate-500">
            Strategy
            <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
              {strategies.length === 0 && <option value="">No strategies</option>}
              {strategies.map((s) => (<option key={s.id} value={s.id}>{s.name} (v{s.current_version})</option>))}
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Method
            <select value={method} onChange={(e) => setMethod(e.target.value as "grid" | "walk_forward")}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
              <option value="grid">Grid Search</option>
              <option value="walk_forward">Walk-Forward</option>
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Target Metric
            <select value={targetMetric} onChange={(e) => setTargetMetric(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
              {METRICS.map((m) => (<option key={m} value={m}>{m}</option>))}
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Start
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            End
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
        </div>
        <label className="mt-3 block text-xs font-medium text-slate-500">
          Parameter Ranges (JSON: key → array of values)
          <textarea
            value={paramRangesText}
            onChange={(e) => setParamRangesText(e.target.value)}
            rows={5}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 font-mono text-xs text-slate-800"
          />
        </label>
        <div className="mt-3 flex items-center gap-3">
          <button onClick={runOptimization} disabled={running || !strategyId}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50">
            {running ? "Running..." : "Run Optimization"}
          </button>
          <span className="text-xs text-slate-400">Max 500 combinations</span>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </Card>

      {selected && selected.status === "completed" && selected.best_params && (
        <Card title="Best Result" subtitle={`Ranked #1 by ${selected.target_metric}`}>
          <div className="mb-3 grid gap-2 sm:grid-cols-4">
            {selected.best_metrics && Object.entries(selected.best_metrics)
              .filter(([k]) => !["status", "error"].includes(k))
              .slice(0, 8)
              .map(([k, v]) => (
                <div key={k} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-400">{k.replace(/_/g, " ")}</p>
                  <p className={`mt-0.5 text-sm font-semibold tabular-nums ${k.includes("pnl") || k.includes("return") ? ((v as number) >= 0 ? "text-emerald-600" : "text-red-600") : "text-slate-800"}`}>
                    {fmt(v as number)}
                  </p>
                </div>
              ))}
          </div>
          <pre className="rounded bg-slate-50 p-2 text-[11px] text-slate-600 overflow-x-auto">
            {JSON.stringify(selected.best_params, null, 2)}
          </pre>
        </Card>
      )}

      {results.length > 0 && (
        <Card title={`Results (${results.length})`} subtitle={selected?.method === "walk_forward" ? "Sorted by train Sharpe — check test Sharpe for overfitting" : "Sorted by target metric"}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-slate-400">
                <tr>
                  <th className="py-1 pr-3">#</th>
                  <th className="py-1 pr-3">Status</th>
                  <th className="py-1 pr-3">Sharpe</th>
                  <th className="py-1 pr-3">Net P&L</th>
                  <th className="py-1 pr-3">Return</th>
                  <th className="py-1 pr-3">Win Rate</th>
                  <th className="py-1 pr-3">PF</th>
                  <th className="py-1 pr-3">Max DD</th>
                  <th className="py-1 pr-3">Trades</th>
                  {selected?.method === "walk_forward" && <th className="py-1 pr-3">Train Sharpe</th>}
                  {selected?.method === "walk_forward" && <th className="py-1 pr-3">Test Sharpe</th>}
                  <th className="py-1">Params</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {results.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100">
                    <td className="py-1 pr-3 text-slate-400">{r.rank}</td>
                    <td className="py-1 pr-3"><Badge tone={r.status === "completed" ? "green" : "red"}>{r.status}</Badge></td>
                    <td className="py-1 pr-3 font-medium">{fmt(r.sharpe_ratio)}</td>
                    <td className={`py-1 pr-3 ${(r.net_pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"}`}>{fmt(r.net_pnl)}</td>
                    <td className="py-1 pr-3">{fmt(r.return_pct)}%</td>
                    <td className="py-1 pr-3">{fmt(r.win_rate)}%</td>
                    <td className="py-1 pr-3">{fmt(r.profit_factor)}</td>
                    <td className="py-1 pr-3 text-red-600">{fmt(r.max_drawdown_pct)}%</td>
                    <td className="py-1 pr-3">{r.total_trades}</td>
                    {selected?.method === "walk_forward" && <td className="py-1 pr-3">{fmt(r.train_sharpe)}</td>}
                    {selected?.method === "walk_forward" && <td className="py-1 pr-3">{fmt(r.test_sharpe)}</td>}
                    <td className="max-w-[200px] truncate text-[11px] text-slate-500">{JSON.stringify(r.params)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title="Run History" subtitle="Previous optimization runs">
        {completed.length === 0 ? (
          <p className="text-xs text-slate-500">No optimization runs yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {completed.map((r) => (
              <li key={r.id}>
                <button onClick={() => loadRun(r.id)}
                  className="flex w-full items-center justify-between gap-3 py-2 text-left text-xs hover:bg-slate-50">
                  <span className="flex items-center gap-2">
                    <Badge tone="green">{r.method}</Badge>
                    <span className="text-slate-400">{r.total_combinations} combos</span>
                    <span className="text-slate-400">{new Date(r.created_at).toLocaleString()}</span>
                  </span>
                  {r.best_metrics && (
                    <span className="tabular-nums font-medium text-slate-600">
                      Best {r.target_metric}: {fmt(r.best_metrics[r.target_metric] as number)}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
