"use client";

import { useEffect, useState } from "react";
import { api, type BacktestRun, type Health, type Strategy } from "@/lib/api";
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
  { step: "Build", detail: "Visual · Technical · Flow", ready: true },
  { step: "Backtest", detail: "Historical simulation", ready: true },
  { step: "Debug / Analyze", detail: "Why did it enter?", ready: false },
  { step: "Forward Test", detail: "Paper · live data", ready: false },
  { step: "Optimize", detail: "Grid · walk-forward", ready: false },
  { step: "Compare", detail: "Versions side-by-side", ready: false },
];

export function DashboardView() {
  const { user } = useAuth();
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [backtestCount, setBacktestCount] = useState<number | null>(null);
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
      .then((runs) => {
        if (!cancelled) setBacktestCount(runs.length);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user]);

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
        <MetricCard label="Virtual Capital" value="—" hint="Create a paper account" />
        <MetricCard label="Today's P&L" value="—" hint="No open paper positions" />
        <MetricCard label="Total P&L" value="—" hint="No closed trades yet" />
        <MetricCard
          label="Active Strategies"
          value={strategies ? String(strategies.length) : "0"}
          hint={user ? undefined : "Sign in to sync"}
        />
        <MetricCard label="Running Forward Tests" value="0" hint="Engine ships in Phase 7" />
        <MetricCard
          label="Total Backtests"
          value={backtestCount === null ? "0" : String(backtestCount)}
          hint={backtestCount === 0 ? "Run one from the Backtest page" : undefined}
        />
        <MetricCard label="Best Strategy" value="—" hint="Run a backtest first" />
        <MetricCard label="Max Portfolio Drawdown" value="—" hint="Requires trade history" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* Strategy status */}
        <Card
          title="Strategy Status"
          subtitle="All strategies and their lifecycle state"
          className="xl:col-span-2"
          actions={
            <a
              href="/strategies"
              className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              View all
            </a>
          }
        >
          {!user ? (
            <p className="py-8 text-center text-sm text-slate-400">
              Sign in to view and manage your strategies.
            </p>
          ) : strategies === null ? (
            <p className="py-8 text-center text-sm text-slate-400">
              {loadError ?? "Loading strategies…"}
            </p>
          ) : strategies.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">
              No strategies yet. The Visual Builder ships in Phase 4 — until then you can create
              placeholder strategies from the Strategies page.
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
                      <td className="py-2 pr-3 text-slate-400">—</td>
                      <td className="py-2 text-slate-400">—</td>
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
