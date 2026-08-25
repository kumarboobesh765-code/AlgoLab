"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type BacktestRun,
  type ForwardTestRun,
  type Health,
  type PaperAccount,
  type PaperAccountDetail,
  type Strategy,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";
import { Badge, StatusBadge } from "@/components/ui/Badge";

function ApiStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const h = await api<Health>("/health");
        if (!cancelled) setHealth(h);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "API unreachable");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <Badge tone="red">
        <span className="h-1.5 w-1.5 rounded-full bg-red-500" /> API offline
      </Badge>
    );
  }
  if (!health) {
    return <Badge>Checking API…</Badge>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone={health.database === "ok" ? "green" : "red"}>
        <span
          className={`h-1.5 w-1.5 rounded-full ${health.database === "ok" ? "bg-emerald-500" : "bg-red-500"}`}
        />
        API {health.status}
      </Badge>
      {health.market_data_is_demo && <Badge tone="amber">DEMO DATA — synthetic</Badge>}
      <Badge tone="blue">{health.trading_mode.replace("_", " ")}</Badge>
    </div>
  );
}

const WORKFLOW = [
  { step: "Build", detail: "Visual · Technical · Flow · AI", ready: true },
  { step: "Backtest", detail: "Historical simulation", ready: true },
  { step: "Debug / Analyze", detail: "Replay bar by bar", ready: true },
  { step: "Forward Test", detail: "Paper · auto-ticked", ready: true },
  { step: "Optimize", detail: "Grid · walk-forward", ready: true },
  { step: "Compare", detail: "Versions side-by-side", ready: true },
];

export function DashboardView() {
  const { user } = useAuth();
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [backtestCount, setBacktestCount] = useState<number | null>(null);
  const [runningFtCount, setRunningFtCount] = useState<number | null>(null);
  const [paperStats, setPaperStats] = useState<{
    capital: number;
    today: number;
    total: number;
    accounts: number;
  } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api<Strategy[]>("/strategies")
      .then((s) => {
        if (!cancelled) setStrategies(s);
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load");
      });
    api<BacktestRun[]>("/backtests")
      .then((rs) => {
        if (!cancelled) {
          setRuns(rs);
          setBacktestCount(rs.length);
        }
      })
      .catch(() => {});
    api<ForwardTestRun[]>("/forward-tests?status_filter=running")
      .then((rs) => {
        if (!cancelled) setRunningFtCount(rs.length);
      })
      .catch(() => {});
    (async () => {
      try {
        const accounts = await api<PaperAccount[]>("/paper/accounts");
        if (accounts.length === 0) return;
        const todayStr = new Date().toISOString().slice(0, 10);
        let capital = 0;
        let totalPnl = 0;
        let todayPnl = 0;
        for (const account of accounts) {
          const detail = await api<PaperAccountDetail>(`/paper/accounts/${account.id}`);
          capital += account.initial_capital;
          totalPnl += detail.equity - account.initial_capital;
          const closedToday = detail.closed_positions
            .filter((p) => p.status === "closed" && p.exit_time?.slice(0, 10) === todayStr)
            .reduce((sum, p) => sum + (p.realized_pnl ?? 0), 0);
          todayPnl += closedToday + detail.unrealized_pnl;
        }
        if (!cancelled) setPaperStats({ capital, today: todayPnl, total: totalPnl, accounts: accounts.length });
      } catch {
        /* paper stats are optional dashboard sugar */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const completedRuns = useMemo(
    () => runs.filter((r) => r.status === "completed" && r.result_summary),
    [runs],
  );

  const bestStrategy = useMemo(() => {
    if (completedRuns.length === 0 || !strategies) return null;
    let top = completedRuns[0];
    for (const r of completedRuns) {
      if (r.result_summary!.summary.return_pct > top.result_summary!.summary.return_pct) top = r;
    }
    const name =
      strategies.find((s) => s.id === top.strategy_id)?.name ?? top.strategy_id.slice(0, 8);
    return { name, ret: top.result_summary!.summary.return_pct };
  }, [completedRuns, strategies]);

  const worstDrawdown = useMemo(() => {
    if (completedRuns.length === 0) return null;
    return Math.max(...completedRuns.map((r) => r.result_summary!.summary.max_drawdown_pct));
  }, [completedRuns]);

  const latestRunByStrategy = useMemo(() => {
    const map = new Map<string, { trades: number; winRate: number }>();
    for (const r of runs) {
      if (r.status !== "completed" || !r.result_summary) continue;
      map.set(r.strategy_id, {
        trades: r.result_summary.summary.total_trades,
        winRate: r.result_summary.summary.win_rate,
      });
    }
    return map;
  }, [runs]);

  return (
    <div className="space-y-5">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            Welcome{user ? `, ${user.email}` : ""}
          </h2>
          <p className="text-xs text-slate-500">
            Research + backtesting + paper trading platform. Live trading is not available in V1.
          </p>
        </div>
        <ApiStatus />
      </div>

      {/* Top metrics */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="Virtual Capital"
          value={paperStats ? paperStats.capital.toLocaleString("en-IN") : "—"}
          hint={paperStats ? `${paperStats.accounts} paper account${paperStats.accounts > 1 ? "s" : ""}` : "Create a paper account"}
        />
        <MetricCard
          label="Today's P&L"
          value={paperStats ? `${paperStats.today >= 0 ? "+" : "-"}₹${Math.abs(paperStats.today).toLocaleString("en-IN")}` : "—"}
          tone={paperStats ? (paperStats.today >= 0 ? "positive" : "negative") : "neutral"}
          hint="Open + closed today"
        />
        <MetricCard
          label="Total Paper P&L"
          value={paperStats ? `${paperStats.total >= 0 ? "+" : "-"}₹${Math.abs(paperStats.total).toLocaleString("en-IN")}` : "—"}
          tone={paperStats ? (paperStats.total >= 0 ? "positive" : "negative") : "neutral"}
          hint="Equity vs deposited capital"
        />
        <MetricCard
          label="Active Strategies"
          value={strategies ? String(strategies.length) : "0"}
        />
        <MetricCard
          label="Running Forward Tests"
          value={runningFtCount === null ? "0" : String(runningFtCount)}
          hint="auto-ticked by the scheduler"
        />
        <MetricCard
          label="Total Backtests"
          value={backtestCount === null ? "0" : String(backtestCount)}
          hint={backtestCount === 0 ? "Run one from the Backtest page" : undefined}
        />
        <MetricCard
          label="Best Strategy"
          value={bestStrategy ? bestStrategy.name : "—"}
          hint={bestStrategy ? `+${bestStrategy.ret.toFixed(2)}% best backtest return` : "Run a backtest first"}
        />
        <MetricCard
          label="Worst Backtest DD"
          value={worstDrawdown !== null ? `-${worstDrawdown.toFixed(2)}%` : "—"}
          hint="Deepest drawdown across backtests"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* Strategy status */}
        <Card
          title="Strategy Status"
          subtitle="All strategies and their lifecycle state"
          className="xl:col-span-2"
          actions={
            <Link
              href="/strategies"
              className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              View all
            </Link>
          }
        >
          {!user ? (
            <p className="py-8 text-center text-sm text-slate-400">Connecting to the API…</p>
          ) : strategies === null ? (
            <p className="py-8 text-center text-sm text-slate-400">
              {loadError ?? "Loading strategies…"}
            </p>
          ) : strategies.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">
              No strategies yet — create one in the Visual Builder or start from a template in the
              Strategy Library.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-[13px]">
                <thead>
                  <tr className="border-b border-slate-100 text-[11px] uppercase tracking-wide text-slate-400">
                    <th className="pb-2 pr-3 font-medium">Strategy</th>
                    <th className="pb-2 pr-3 font-medium">Ver</th>
                    <th className="pb-2 pr-3 font-medium">Market</th>
                    <th className="pb-2 pr-3 font-medium">Status</th>
                    <th className="pb-2 pr-3 font-medium">Trades</th>
                    <th className="pb-2 font-medium">Win rate</th>
                  </tr>
                </thead>
                <tbody>
                  {strategies.slice(0, 8).map((s) => (
                    <tr key={s.id} className="border-b border-slate-50 last:border-0">
                      <td className="py-2 pr-3 font-medium text-slate-800">{s.name}</td>
                      <td className="py-2 pr-3 tabular-nums text-slate-500">v{s.current_version}</td>
                      <td className="py-2 pr-3 text-slate-600">
                        {s.exchange} · {s.underlying}
                      </td>
                      <td className="py-2 pr-3">
                        <StatusBadge status={s.status} />
                      </td>
                      <td className="py-2 pr-3 tabular-nums text-slate-600">
                        {latestRunByStrategy.has(s.id) ? latestRunByStrategy.get(s.id)!.trades : "—"}
                      </td>
                      <td className="py-2 tabular-nums text-slate-600">
                        {latestRunByStrategy.has(s.id)
                          ? `${latestRunByStrategy.get(s.id)!.winRate.toFixed(1)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Workflow */}
        <Card title="Platform Workflow" subtitle="Build → Backtest → Forward Test → Grow">
          <ol className="space-y-2">
            {WORKFLOW.map((w, i) => (
              <li key={w.step} className="flex items-center gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-50 text-[11px] font-semibold text-blue-700 ring-1 ring-inset ring-blue-200">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-slate-700">{w.step}</p>
                  <p className="truncate text-[11px] text-slate-400">{w.detail}</p>
                </div>
                <Badge tone={w.ready ? "green" : "slate"}>{w.ready ? "Ready" : "Planned"}</Badge>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
