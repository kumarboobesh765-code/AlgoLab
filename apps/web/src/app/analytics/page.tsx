"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { BacktestRun, OptimizationRun, Strategy } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";

function fmtMoney(n: number): string {
  return `${n < 0 ? "-" : ""}₹${Math.abs(Math.round(n)).toLocaleString("en-IN")}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export default function AnalyticsPage() {
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [opts, setOpts] = useState<OptimizationRun[]>([]);

  useEffect(() => {
    if (!auth.user) return;
    Promise.all([
      api<BacktestRun[]>("/backtests"),
      api<Strategy[]>("/strategies"),
      api<OptimizationRun[]>("/optimizations"),
    ])
      .then(([r, s, o]) => {
        setRuns(r);
        setStrategies(s);
        setOpts(o);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [auth.user]);

  const data = useMemo(() => {
    const nameById = new Map(strategies.map((s) => [s.id, s.name]));
    const completed = runs.filter((r) => r.status === "completed" && r.result_summary);

    const latestByStrategy = new Map<string, BacktestRun>();
    for (const run of completed) {
      const prev = latestByStrategy.get(run.strategy_id);
      if (!prev || run.created_at > prev.created_at) latestByStrategy.set(run.strategy_id, run);
    }
    const latest = [...latestByStrategy.values()].sort(
      (a, b) =>
        (b.result_summary?.summary.return_pct ?? 0) - (a.result_summary?.summary.return_pct ?? 0),
    );

    let netPnl = 0;
    let trades = 0;
    let wins = 0;
    for (const run of latest) {
      netPnl += run.result_summary!.summary.net_pnl;
      trades += run.result_summary!.summary.total_trades;
      wins += run.result_summary!.summary.winning_trades;
    }

    const monthly = new Map<string, number>();
    for (const run of latest) {
      for (const t of run.result_summary!.trades) {
        const month = t.exit_time.slice(0, 7);
        monthly.set(month, (monthly.get(month) ?? 0) + t.pnl);
      }
    }
    const months = [...monthly.entries()].sort(([a], [b]) => a.localeCompare(b));

    const optCompleted = opts.filter((o) => o.status === "completed");
    const bestSharpe = Math.max(
      0,
      ...optCompleted.map((o) => Number(o.best_metrics?.["sharpe_ratio"] ?? 0)),
    );

    return { nameById, completed, latest, netPnl, trades, wins, months, optCompleted, bestSharpe };
  }, [runs, strategies, opts]);

  if (!auth.user) {
    return <p className="text-sm text-slate-500">Sign in to view analytics.</p>;
  }
  if (loading) return <p className="text-sm text-slate-500">Loading analytics…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;

  const winRate = data.trades > 0 ? (data.wins / data.trades) * 100 : null;

  // Monthly P&L chart geometry
  const maxAbs = Math.max(1, ...data.months.map(([, v]) => Math.abs(v)));
  const posTotal = data.months.reduce((acc, [, v]) => acc + Math.max(v, 0), 0);
  const negTotal = data.months.reduce((acc, [, v]) => acc + Math.max(-v, 0), 0);
  const chartH = 180;
  const zeroY =
    posTotal + negTotal > 0 ? 10 + (posTotal / (posTotal + negTotal)) * (chartH - 20) : chartH - 10;
  const barW = data.months.length > 0 ? Math.min(48, 560 / data.months.length - 8) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Analytics</h2>
        <p className="text-sm text-slate-500">
          Aggregated research performance — latest backtest per strategy.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <MetricCard label="Strategies" value={String(strategies.length)} />
        <MetricCard label="Completed runs" value={String(data.completed.length)} />
        <MetricCard
          label="Net P&L"
          value={fmtMoney(data.netPnl)}
          hint="sum of latest runs"
          tone={data.netPnl >= 0 ? "positive" : "negative"}
        />
        <MetricCard
          label="Win rate"
          value={winRate === null ? "—" : `${winRate.toFixed(1)}%`}
          hint={`${data.trades} trades`}
        />
        <MetricCard
          label="Best walk-forward Sharpe"
          value={data.optCompleted.some((o) => o.best_metrics?.sharpe_ratio) ? data.bestSharpe.toFixed(2) : "—"}
          hint={`${opts.length} optimization runs`}
        />
      </div>

      <Card title="Monthly P&L" subtitle="Realized trade P&L by exit month (latest run per strategy)">
        {data.months.length === 0 ? (
          <p className="py-10 text-center text-sm text-slate-400">
            No trades yet — run a backtest first.
          </p>
        ) : (
          <svg viewBox="0 0 640 200" className="w-full">
            <line x1="30" y1={zeroY} x2="630" y2={zeroY} stroke="#cbd5e1" strokeDasharray="4 3" />
            {data.months.map(([month, pnl], i) => {
              const h = (Math.abs(pnl) / maxAbs) * (zeroY - 12);
              const up = pnl >= 0;
              const x = 40 + i * (600 / Math.max(data.months.length, 1));
              return (
                <g key={month}>
                  <rect
                    x={x}
                    y={up ? zeroY - h : zeroY}
                    width={barW}
                    height={Math.max(h, 1.5)}
                    fill={up ? "#10b981" : "#ef4444"}
                    rx="2"
                  >
                    <title>{`${month}: ${fmtMoney(pnl)}`}</title>
                  </rect>
                  <text x={x} y={chartH - 4} fontSize="9" fill="#94a3b8" textAnchor="middle">
                    {month.slice(2)}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </Card>

      <Card
        title="Strategy performance"
        subtitle={`Latest completed run per strategy (${data.latest.length})`}
      >
        {data.latest.length === 0 ? (
          <p className="py-10 text-center text-sm text-slate-400">
            No completed backtests yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-2 py-2">Strategy</th>
                  <th className="px-2 py-2">Market</th>
                  <th className="px-2 py-2 text-right">Return</th>
                  <th className="px-2 py-2 text-right">Net P&L</th>
                  <th className="px-2 py-2 text-right">Win rate</th>
                  <th className="px-2 py-2 text-right">Trades</th>
                  <th className="px-2 py-2">Last run</th>
                  <th className="px-2 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.latest.map((run) => {
                  const s = run.result_summary!.summary;
                  return (
                    <tr key={run.id}>
                      <td className="px-2 py-2 font-medium text-slate-900">
                        {data.nameById.get(run.strategy_id) ?? run.strategy_id.slice(0, 8)}
                      </td>
                      <td className="px-2 py-2 text-slate-500">
                        {run.config?.symbol ?? "—"} · {run.config?.timeframe ?? "—"}
                      </td>
                      <td
                        className={`px-2 py-2 text-right font-medium tabular-nums ${
                          s.return_pct >= 0 ? "text-emerald-600" : "text-red-600"
                        }`}
                      >
                        {fmtPct(s.return_pct)}
                      </td>
                      <td
                        className={`px-2 py-2 text-right tabular-nums ${
                          s.net_pnl >= 0 ? "text-emerald-600" : "text-red-600"
                        }`}
                      >
                        {fmtMoney(s.net_pnl)}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">
                        {s.total_trades > 0
                          ? `${((s.winning_trades / s.total_trades) * 100).toFixed(0)}%`
                          : "—"}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">{s.total_trades}</td>
                      <td className="px-2 py-2 text-slate-500">
                        {new Date(run.created_at).toLocaleDateString("en-IN")}
                      </td>
                      <td className="px-2 py-2">
                        <Link
                          href={`/replay?run=${run.id}`}
                          className="font-medium text-indigo-600 hover:underline"
                        >
                          Replay
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Optimization activity" subtitle={`${opts.length} total runs`}>
        {opts.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">No optimization runs yet.</p>
        ) : (
          <div className="space-y-2">
            {opts.slice(0, 5).map((o) => (
              <div
                key={o.id}
                className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-xs"
              >
                <span className="font-medium text-slate-700">
                  {data.nameById.get(o.strategy_id) ?? o.strategy_id.slice(0, 8)} ·{" "}
                  {o.method.replace("_", " ")} · {o.total_combinations} combos
                </span>
                <Badge tone={o.status === "completed" ? "green" : o.status === "failed" ? "red" : "amber"}>
                  {o.status}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <p className="text-xs text-slate-400">
        Demo market data — aggregates reflect synthetic candles and are for workflow validation only.
      </p>
    </div>
  );
}
