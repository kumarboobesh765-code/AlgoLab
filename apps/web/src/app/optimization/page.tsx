"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type OptimizationCreate,
  type OptimizationResult,
  type OptimizationRun,
  type Strategy,
} from "@/lib/api";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { HeatmapPanel } from "@/components/optimization/HeatmapPanel";
import { downloadCsv } from "@/lib/csv";
import { loadSettings } from "@/lib/settings";

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
  const [trainPct, setTrainPct] = useState(70);
  const [paramRangesText, setParamRangesText] = useState(
    '{\n  "indicators.f.params.length": [5, 10, 15, 20, 25, 30],\n  "indicators.s.params.length": [20, 30, 40, 50]\n}'
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api<Strategy[]>("/strategies").then((all) => {
      const usable = all.filter((s) => s.definition !== null);
      setStrategies(usable);
      if (usable.length > 0) setStrategyId((cur) => cur || usable[0].id);
    }).catch((e: Error) => setLoadError(e.message));
    api<OptimizationRun[]>("/optimizations").then(setRuns).catch((e: Error) =>
      setLoadError(e.message),
    );
  }, []);

  useEffect(() => {
    refresh();
    const runId = new URLSearchParams(window.location.search).get("run");
    if (!runId) return;
    api<OptimizationRun>(`/optimizations/${runId}`)
      .then((run) => {
        setSelected(run);
        if (run.status === "completed") {
          api<OptimizationResult[]>(`/optimizations/${run.id}/results`).then(setResults);
        }
      })
      .catch(() => undefined);
  }, [refresh]);

  // Parameter-key hints derived from the selected strategy's definition
  const paramHints = useMemo(() => {
    const def = strategies.find((s) => s.id === strategyId)?.definition as {
      indicators?: { id: string; params?: Record<string, unknown> }[];
    } | undefined;
    return (def?.indicators ?? []).map((ind) =>
      Object.keys(ind.params ?? {}).map((p) => `indicators.${ind.id}.params.${p}`),
    ).flat();
  }, [strategies, strategyId]);

  async function runOptimization() {
    if (!strategyId) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(paramRangesText);
    } catch {
      setError("Invalid JSON in parameter ranges");
      return;
    }
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed) ||
      Object.entries(parsed as Record<string, unknown>).some(
        ([, v]) =>
          !Array.isArray(v) ||
          v.length === 0 ||
          v.some((x) => typeof x !== "number" || Number.isNaN(x)),
      )
    ) {
      setError(
        "Parameter ranges must be a JSON object mapping keys to non-empty arrays of numbers, e.g. {\"indicators.f.params.length\": [5, 10]}",
      );
      return;
    }
    const paramRanges = parsed as Record<string, number[]>;
    const combos = Object.values(paramRanges).reduce((acc, vals) => acc * vals.length, 1);
    if (combos > 500) {
      setError(`${combos} combinations — exceeds the 500 limit. Trim some ranges.`);
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const s = loadSettings();
      const payload: OptimizationCreate = {
        strategy_id: strategyId,
        method,
        param_ranges: paramRanges,
        start,
        end,
        target_metric: targetMetric,
        initial_capital: s.defaultCapital,
        costs_pct: s.costsPct,
        ...(method === "walk_forward" ? { train_pct: Math.min(Math.max(trainPct, 31), 89) / 100 } : {}),
      };
      const run = await api<OptimizationRun>("/optimizations?background=true", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setRuns([run, ...runs]);
      setSelected(run);
      setResults([]);
      // Poll until the background executor finishes (max ~90 s)
      const deadline = Date.now() + 90_000;
      let final = run;
      while ((final.status === "queued" || final.status === "running") && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 1500));
        final = await api<OptimizationRun>(`/optimizations/${run.id}`);
        setSelected(final);
      }
      if (final.status === "completed") {
        const res = await api<OptimizationResult[]>(`/optimizations/${final.id}/results`);
        setResults(res);
      } else if (final.status !== "completed") {
        setError(`Run finished with status “${final.status}” — see history below.`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Optimization failed");
    } finally {
      setRunning(false);
    }
  }

  async function loadRun(id: string) {
    setError(null);
    try {
      const run = await api<OptimizationRun>(`/optimizations/${id}`);
      setSelected(run);
      setResults([]);
      if (run.status === "completed") {
        const res = await api<OptimizationResult[]>(`/optimizations/${id}/results`);
        setResults(res);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load run");
    }
  }

  const sortedRuns = [...runs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <div className="space-y-4">
      {loadError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-inset ring-red-200">
          {loadError}
        </p>
      )}
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
          {method === "walk_forward" && (
            <label className="block text-xs font-medium text-slate-500">
              Train % (of window)
              <input type="number" min={31} max={89} value={trainPct}
                onChange={(e) => setTrainPct(Number(e.target.value))}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
          )}
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
        {paramHints.length > 0 && (
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <span className="text-[11px] text-slate-400">Valid keys for this strategy:</span>
            {paramHints.map((k) => (
              <span
                key={k}
                title={k}
                className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500"
              >
                {k}
              </span>
            ))}
          </div>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button onClick={runOptimization} disabled={running || !strategyId}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50">
            {running ? "Running..." : "Run Optimization"}
          </button>
          <span className="text-xs text-slate-400">Max 500 combinations</span>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </Card>

      <Card
        title="Sensitivity Heatmap"
        subtitle="Backtest every (x, y) parameter pair — green means better. Spots overfitting at a glance."
      >
        <HeatmapPanel strategyId={strategyId} paramHints={paramHints} start={start} end={end} />
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
        <Card
          title={`Results (${results.length})`}
          subtitle={selected?.method === "walk_forward" ? "Sorted by train Sharpe — check test Sharpe for overfitting" : "Sorted by target metric"}
          actions={
            <button
              onClick={() =>
                downloadCsv(
                  `optimization_${selected?.id.slice(0, 8) ?? "run"}.csv`,
                  ["rank", "status", "sharpe", "net_pnl", "return_pct", "win_rate", "profit_factor", "max_drawdown_pct", "trades", "train_sharpe", "test_sharpe", "params"],
                  results.map((r) => [
                    r.rank, r.status, r.sharpe_ratio, r.net_pnl, r.return_pct, r.win_rate,
                    r.profit_factor, r.max_drawdown_pct, r.total_trades, r.train_sharpe ?? "",
                    r.test_sharpe ?? "", JSON.stringify(r.params),
                  ]),
                )
              }
              className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50"
            >
              Export CSV
            </button>
          }
        >
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
        {sortedRuns.length === 0 ? (
          <p className="text-xs text-slate-500">No optimization runs yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {sortedRuns.map((r) => (
              <li key={r.id}>
                <button onClick={() => loadRun(r.id)}
                  className="flex w-full items-center justify-between gap-3 py-2 text-left text-xs hover:bg-slate-50">
                  <span className="flex items-center gap-2">
                    <Badge tone="blue">{r.method}</Badge>
                    <StatusBadge status={r.status} />
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
