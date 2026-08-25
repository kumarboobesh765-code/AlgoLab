"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type BacktestResults,
  type BacktestRun,
  type Strategy,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { downloadCsv } from "@/lib/csv";
import { useAppSettings } from "@/lib/settings";

function todayISO(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const EXIT_TONES: Record<string, "red" | "green" | "amber" | "slate"> = {
  target: "green",
  signal: "slate",
  stop_loss: "red",
  trailing_stop: "amber",
  end_of_data: "slate",
};

function fmtMoney(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function MetricCard({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: string;
  tone?: "slate" | "green" | "red";
}) {
  const toneClass =
    tone === "green"
      ? "text-emerald-600"
      : tone === "red"
        ? "text-red-600"
        : "text-slate-800";
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}

function EquityCurve({ results }: { results: BacktestResults }) {
  const pts = results.equity_curve;
  if (pts.length < 2) return null;
  const w = 720;
  const h = 200;
  const pad = 8;
  const values = pts.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (pts.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - 2 * pad);
  const path = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`)
    .join(" ");
  const up = results.summary.net_pnl >= 0;
  const stroke = up ? "#059669" : "#dc2626";
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Equity curve">
        <line
          x1={pad}
          y1={y(results.summary.initial_capital)}
          x2={w - pad}
          y2={y(results.summary.initial_capital)}
          stroke="#cbd5e1"
          strokeDasharray="4 4"
          strokeWidth="1"
        />
        <path d={path} fill="none" stroke={stroke} strokeWidth="1.8" />
      </svg>
      <div className="flex justify-between text-[11px] text-slate-400">
        <span>low {fmtMoney(min)}</span>
        <span>start {fmtMoney(results.summary.initial_capital)}</span>
        <span>high {fmtMoney(max)}</span>
      </div>
    </div>
  );
}

export default function BacktestPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [start, setStart] = useState(todayISO(-30));
  const [end, setEnd] = useState(todayISO(-1));
  const savedSettings = useAppSettings();
  // null = follow saved settings until the user edits the field
  const [capitalDraft, setCapitalDraft] = useState<string | null>(null);
  const [costsDraft, setCostsDraft] = useState<string | null>(null);
  const capital = capitalDraft ?? String(savedSettings.defaultCapital);
  const costs = costsDraft ?? String(savedSettings.costsPct);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [history, setHistory] = useState<BacktestRun[]>([]);

  const refreshHistory = useCallback(() => {
    api<BacktestRun[]>("/backtests")
      .then(setHistory)
      .catch((e) =>
        setLoadError(e instanceof Error ? e.message : "Could not load backtest history"),
      );
  }, []);

  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("strategy");
    api<Strategy[]>("/strategies")
      .then((all) => {
        const usable = all.filter((st) => st.definition !== null);
        setStrategies(usable);
        if (usable.length > 0) {
          setStrategyId(
            (cur) => cur || (wanted && usable.some((st) => st.id === wanted) ? wanted : usable[0].id),
          );
        }
      })
      .catch((e) =>
        setLoadError(e instanceof Error ? e.message : "Could not load strategies"),
      );
    refreshHistory();
  }, [refreshHistory]);

  const selected = useMemo(
    () => strategies.find((st) => st.id === strategyId),
    [strategies, strategyId],
  );

  async function runBacktest() {
    if (!strategyId) return;
    setRunning(true);
    setError(null);
    try {
      const created = await api<BacktestRun>("/backtests", {
        method: "POST",
        body: JSON.stringify({
          strategy_id: strategyId,
          start,
          end,
          initial_capital: Number(capital) > 0 ? Number(capital) : savedSettings.defaultCapital,
          costs_pct: Number(costs) >= 0 ? Number(costs) : savedSettings.costsPct,
        }),
      });
      setRun(created);
      refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  }

  async function loadRun(id: string) {
    try {
      setRun(await api<BacktestRun>(`/backtests/${id}`));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load that run");
    }
  }

  const results = run?.result_summary ?? null;
  const s = results?.summary ?? null;

  return (
    <div className="space-y-4">
      {loadError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {loadError}
        </p>
      )}
      <Card
        title="Run a backtest"
        subtitle="Simulates the strategy definition over stored candles — ingest history via Data Manager first."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <label className="lg:col-span-2 block text-xs font-medium text-slate-500">
            Strategy
            <select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            >
              {strategies.length === 0 && (
                <option value="">No strategies with definitions</option>
              )}
              {strategies.map((st) => (
                <option key={st.id} value={st.id}>
                  {st.name} (v{st.current_version})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Start
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            End
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Capital
            <input
              type="number"
              value={capital}
              min="1"
              onChange={(e) => setCapitalDraft(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Costs % / side
            <input
              type="number"
              value={costs}
              step="0.01"
              min="0"
              onChange={(e) => setCostsDraft(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={runBacktest}
            disabled={running || !strategyId}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {running ? "Running..." : "Run backtest"}
          </button>
          {selected && (
            <span className="text-xs text-slate-400">
              {selected.underlying} · {selected.strategy_type}
            </span>
          )}
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </Card>

      {run && results && s && (
        <Card
          title={`Result — ${s.timeframe} candles`}
          subtitle={
            run.config
              ? `${run.config.symbol} · ${run.config.start} to ${run.config.end} · ${run.config.bars} bars · v${run.version_number}`
              : undefined
          }
          actions={
            <Badge tone={run.status === "completed" ? "green" : "red"}>{run.status}</Badge>
          }
        >
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <MetricCard
              label="Net P&L"
              value={`${s.net_pnl >= 0 ? "+" : ""}${fmtMoney(s.net_pnl)}`}
              tone={s.net_pnl >= 0 ? "green" : "red"}
            />
            <MetricCard
              label="Return"
              value={`${s.return_pct >= 0 ? "+" : ""}${s.return_pct}%`}
              tone={s.return_pct >= 0 ? "green" : "red"}
            />
            <MetricCard label="Win rate" value={`${s.win_rate}%`} />
            <MetricCard label="Trades" value={`${s.total_trades}`} />
            <MetricCard label="Profit factor" value={`${s.profit_factor}`} />
            <MetricCard label="Max drawdown" value={`${s.max_drawdown_pct}%`} tone="red" />
            <MetricCard label="Final equity" value={fmtMoney(s.final_equity)} />
            <MetricCard label="Sharpe" value={`${s.sharpe_ratio}`} />
            <MetricCard label="Avg win" value={fmtMoney(s.avg_win)} tone="green" />
            <MetricCard label="Avg loss" value={fmtMoney(s.avg_loss)} tone="red" />
            <MetricCard label="Costs" value={fmtMoney(s.total_costs)} />
            {s.cost_breakdown && (
              <Card title="Cost breakdown (INR)" subtitle="Estimated transaction charges">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
                  {Object.entries(s.cost_breakdown).map(([k, v]) => (
                    <MetricCard key={k} label={k.toUpperCase()} value={fmtMoney(v)} />
                  ))}
                </div>
              </Card>
            )}
            <MetricCard label="Largest loss" value={fmtMoney(s.largest_loss)} tone="red" />
          </div>

          <h3 className="mt-4 mb-1 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400">
            <span>Equity curve</span>
            <button
              onClick={() =>
                downloadCsv(
                  `equity_${selected?.id.slice(0, 8) ?? "run"}.csv`,
                  ["time", "equity"],
                  results.equity_curve.map((p) => [p.time, p.equity]),
                )
              }
              className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] font-medium normal-case text-slate-600 hover:bg-slate-50"
            >
              Export CSV
            </button>
          </h3>
          <EquityCurve results={results} />

          <h3 className="mt-4 mb-1 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400">
            <span>Trades ({results.trades.length})</span>
            {results.trades.length > 0 && (
              <button
                onClick={() =>
                  downloadCsv(
                    `trades_${selected?.id.slice(0, 8) ?? "run"}.csv`,
                    ["#", "direction", "entry_time", "exit_time", "qty", "entry_price", "exit_price", "pnl", "pnl_pct", "bars_held", "exit_reason"],
                    results.trades.map((t, i) => [
                      i + 1, t.direction, t.entry_time, t.exit_time, t.quantity,
                      t.entry_price, t.exit_price, t.pnl, t.pnl_pct, t.bars_held, t.exit_reason,
                    ]),
                  )
                }
                className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] font-medium normal-case text-slate-600 hover:bg-slate-50"
              >
                Export CSV
              </button>
            )}
          </h3>
          {results.trades.length === 0 ? (
            <p className="text-xs text-slate-500">No trades were generated in this range.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-slate-400">
                  <tr>
                    <th className="py-1 pr-3">#</th>
                    <th className="py-1 pr-3">Side</th>
                    <th className="py-1 pr-3">Entry</th>
                    <th className="py-1 pr-3">Exit</th>
                    <th className="py-1 pr-3">Qty</th>
                    <th className="py-1 pr-3">In price</th>
                    <th className="py-1 pr-3">Out price</th>
                    <th className="py-1 pr-3">P&L</th>
                    <th className="py-1 pr-3">P&L %</th>
                    <th className="py-1 pr-3">Bars</th>
                    <th className="py-1">Reason</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {results.trades.map((t, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="py-1 pr-3 text-slate-400">{i + 1}</td>
                      <td className="py-1 pr-3">{t.direction}</td>
                      <td className="py-1 pr-3 text-slate-500">
                        {t.entry_time.slice(0, 16).replace("T", " ")}
                      </td>
                      <td className="py-1 pr-3 text-slate-500">
                        {t.exit_time.slice(0, 16).replace("T", " ")}
                      </td>
                      <td className="py-1 pr-3">{t.quantity}</td>
                      <td className="py-1 pr-3">{t.entry_price}</td>
                      <td className="py-1 pr-3">{t.exit_price}</td>
                      <td
                        className={`py-1 pr-3 font-medium ${t.pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}
                      >
                        {t.pnl >= 0 ? "+" : ""}
                        {fmtMoney(t.pnl)}
                      </td>
                      <td
                        className={`py-1 pr-3 ${t.pnl_pct >= 0 ? "text-emerald-600" : "text-red-600"}`}
                      >
                        {t.pnl_pct >= 0 ? "+" : ""}
                        {t.pnl_pct}%
                      </td>
                      <td className="py-1 pr-3 text-slate-500">{t.bars_held}</td>
                      <td className="py-1">
                        <Badge tone={EXIT_TONES[t.exit_reason] ?? "slate"}>{t.exit_reason}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Card title="Run history" subtitle="Latest backtests across all strategies">
        {history.length === 0 ? (
          <p className="text-xs text-slate-500">
            {loadError ? "History unavailable — check the error above." : "No backtest runs yet."}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {history.map((h) => {
              const hs = h.result_summary?.summary;
              return (
                <li key={h.id} className="group flex items-center">
                  <button
                    onClick={() => loadRun(h.id)}
                    className="flex flex-1 items-center justify-between gap-3 py-2 text-left text-xs hover:bg-slate-50"
                  >
                    <span className="flex items-center gap-2">
                      <Badge
                        tone={
                          h.status === "completed" ? "green" : h.status === "failed" ? "red" : "amber"
                        }
                      >
                        {h.status}
                      </Badge>
                      <span className="font-medium text-slate-700">
                        {h.config?.symbol ?? "?"} · {h.config?.timeframe ?? "?"} · v{h.version_number}
                      </span>
                      <span className="text-slate-400">{new Date(h.created_at).toLocaleString()}</span>
                    </span>
                    {hs && (
                      <span
                        className={`tabular-nums font-medium ${hs.net_pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}
                      >
                        {hs.net_pnl >= 0 ? "+" : ""}
                        {fmtMoney(hs.net_pnl)} ({hs.total_trades} trades)
                      </span>
                    )}
                  </button>
                  {h.status !== "running" && (
                    <button
                      onClick={async () => {
                        if (!window.confirm("Delete this backtest run?")) return;
                        try {
                          await api(`/backtests/${h.id}`, { method: "DELETE" });
                          setHistory((cur) => cur.filter((x) => x.id !== h.id));
                          if (run?.id === h.id) setRun(null);
                        } catch (e) {
                          setError(e instanceof Error ? e.message : "Delete failed");
                        }
                      }}
                      title="Delete run"
                      className="ml-2 hidden rounded border border-red-200 px-1.5 py-0.5 text-[11px] text-red-500 group-hover:block hover:bg-red-50"
                    >
                      Delete
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
