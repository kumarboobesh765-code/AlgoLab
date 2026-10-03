"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { api, type BacktestRun, type Strategy } from "@/lib/api";

interface Candidate {
  rank: number;
  run_ids: string[];
  strategy_names: string[];
  metrics: Record<string, number>;
}

interface SubsetResult {
  objective: string;
  exhaustive: boolean;
  subset_size: number;
  candidates_considered: number;
  combinations_possible: number;
  best: Candidate | null;
  runners_up: Candidate[];
  single_best: Candidate | null;
  note: string | null;
}

const OBJECTIVES = [
  { value: "sharpe_ratio", label: "Sharpe ratio" },
  { value: "return_pct", label: "Total return" },
  { value: "calmar", label: "Return / drawdown (Calmar)" },
];

/**
 * Portfolio subset picker.
 *
 * Scores candidate strategy groups on how they perform *together* rather than
 * summing individual returns, so strategies that peaked in the same month are
 * correctly treated as one bet instead of two. Always shows the best single run
 * alongside the best subset: a combination that fails to beat its own best
 * component has not earned its place, and the panel says so.
 */
export function SubsetOptimiser() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [size, setSize] = useState(2);
  const [objective, setObjective] = useState("sharpe_ratio");
  const [result, setResult] = useState<SubsetResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [all, history] = await Promise.all([
          api<Strategy[]>("/strategies"),
          api<BacktestRun[]>("/backtests"),
        ]);
        if (cancelled) return;
        setStrategies(all);
        // Only completed runs can be combined.
        setRuns(history.filter((r) => r.status === "completed"));
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load strategies");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = useCallback((runId: string) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
    setResult(null);
  }, []);

  const optimise = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api<SubsetResult>("/portfolio/optimise-subset", {
        method: "POST",
        body: JSON.stringify({
          run_ids: [...picked],
          size,
          objective,
        }),
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Optimisation failed");
    } finally {
      setBusy(false);
    }
  }, [picked, size, objective]);

  const bestValue = result?.best?.metrics?.[objective] ?? 0;
  const singleValue = result?.single_best?.metrics?.[objective] ?? 0;
  const subsetBeatsSingle =
    result?.best && result.best.run_ids.length > 1 ? bestValue > singleValue : null;

  if (strategies.length === 0) {
    return (
      <Card title="Portfolio subset optimiser">
        <p className="text-sm text-slate-500">
          Create and backtest a few strategies first — the optimiser compares completed runs.
        </p>
      </Card>
    );
  }

  if (runs.length === 0) {
    return (
      <Card title="Portfolio subset optimiser">
        <p className="text-sm text-slate-500">
          No completed backtests yet. Run a backtest, then return here to pick which
          strategies to run together.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <Card
        title="Portfolio subset optimiser"
        subtitle="Finds the combination that performs best together, not just the sum of its parts."
      >
        <div className="grid gap-4 lg:grid-cols-[2fr,1fr]">
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">
              Select completed backtests ({picked.size} selected)
            </p>
            <div className="max-h-64 space-y-1 overflow-auto rounded-lg border border-slate-200 p-2">
              {runs.map((run) => {
                const strat = strategies.find((s) => s.id === run.strategy_id);
                const checked = picked.has(run.id);
                return (
                  <label
                    key={run.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(run.id)}
                    />
                    <span className="flex-1 text-xs text-slate-700">
                      {strat?.name ?? "Unknown strategy"}
                      <span className="ml-1 text-[10px] text-slate-400">
                        {run.config?.timeframe ?? ""}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <div>
              <label className="mb-1 block text-[11px] font-medium text-slate-500">
                Group size
              </label>
              <input
                type="number"
                min={1}
                max={Math.max(1, picked.size)}
                value={size}
                onChange={(e) => setSize(Math.max(1, Number(e.target.value) || 1))}
                className="w-24 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-medium text-slate-500">
                Optimise for
              </label>
              <select
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              >
                {OBJECTIVES.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={optimise}
              disabled={busy || picked.size === 0}
              className="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {busy ? "Searching…" : "Find best subset"}
            </button>
          </div>
        </div>

        {error && (
          <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
            {error}
          </p>
        )}
      </Card>

      {result && result.best && (
        <Card
          title={`Best group of ${result.subset_size}`}
          subtitle={
            result.exhaustive
              ? `Exhaustive search over all ${result.combinations_possible} combinations`
              : `Greedy search — ${result.combinations_possible} combinations is too many to enumerate`
          }
        >
          <div className="space-y-2">
            {result.best.strategy_names.map((name, i) => (
              <span key={i} className="mr-1.5">
                <Badge tone="blue">{name}</Badge>
              </span>
            ))}
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-4">
            <Metric label="Return" value={`${result.best.metrics.return_pct ?? 0}%`} />
            <Metric label="Sharpe" value={String(result.best.metrics.sharpe_ratio ?? 0)} />
            <Metric
              label="Max drawdown"
              value={`${result.best.metrics.max_drawdown_pct ?? 0}%`}
            />
            <Metric label="Trades" value={String(result.best.metrics.total_trades ?? 0)} />
          </div>

          {subsetBeatsSingle !== null && (
            <p
              className={`mt-3 rounded-md px-3 py-2 text-xs ring-1 ring-inset ${
                subsetBeatsSingle
                  ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                  : "bg-amber-50 text-amber-700 ring-amber-200"
              }`}
            >
              {subsetBeatsSingle ? (
                <>
                  This group beats its strongest single strategy ({bestValue.toFixed(2)} vs{" "}
                  {singleValue.toFixed(2)} on {OBJECTIVES.find((o) => o.value === objective)?.label}).
                  The strategies are adding something together.
                </>
              ) : (
                <>
                  This group does <strong>not</strong> beat its strongest single strategy (
                  {bestValue.toFixed(2)} vs {singleValue.toFixed(2)}). The picks are too
                  correlated to count as diversification — consider spreading across
                  different instruments or timeframes.
                </>
              )}
            </p>
          )}

          {result.note && (
            <p className="mt-2 text-[11px] text-slate-500">{result.note}</p>
          )}

          {result.runners_up.length > 0 && (
            <details className="mt-3 text-xs">
              <summary className="cursor-pointer text-indigo-600 hover:underline">
                Other combinations ({result.runners_up.length})
              </summary>
              <table className="mt-2 w-full text-left">
                <thead>
                  <tr className="text-[10px] uppercase text-slate-400">
                    <th className="py-1">#</th>
                    <th>Strategies</th>
                    <th className="text-right">Return</th>
                    <th className="text-right">Sharpe</th>
                  </tr>
                </thead>
                <tbody>
                  {result.runners_up.map((c) => (
                    <tr key={c.rank} className="border-t border-slate-100">
                      <td className="py-1 text-slate-400">{c.rank}</td>
                      <td>{c.strategy_names.join(", ")}</td>
                      <td className="text-right">{c.metrics.return_pct ?? 0}%</td>
                      <td className="text-right">{c.metrics.sharpe_ratio ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </Card>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}