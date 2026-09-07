"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { PortfolioBacktestOut, Strategy } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui/Card";
import { EquityCurveChart } from "@/components/reports/EquityCurveChart";
import { MetricCompareTable } from "@/components/reports/MetricCompareTable";

const SERIES_COLORS = [
  "#3b82f6",
  "#8b5cf6",
  "#10b981",
  "#f59e0b",
];

function todayISO(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function ComparePage() {
  const auth = useAuth();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [start, setStart] = useState(todayISO(-30));
  const [end, setEnd] = useState(todayISO(-1));
  const [capital] = useState("1000000");
  const [costs] = useState("0.05");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PortfolioBacktestOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!auth.user) return;
    api<Strategy[]>("/strategies")
      .then((all) => {
        const usable = all.filter((s) => s.definition !== null);
        setStrategies(usable);
      })
      .catch(() => {});
  }, [auth.user]);

  const completed = useMemo(
    () =>
      (result?.strategies.filter((s) => s.status === "completed") ?? []).map(
        (s) => ({
          ...s,
          strategy_name:
            strategies.find((st) => st.id === s.strategy_id)?.name ??
            s.strategy_name,
        }),
      ),
    [result, strategies],
  );

  const series = useMemo(() => {
    if (completed.length === 0) return [];
    return completed.map((s, i) => {
      const base = s.equity_curve[0]?.equity ?? 1;
      const normalized = s.equity_curve.map((p) => ({
        time: p.time,
        equity: base === 0 ? 0 : ((p.equity - base) / base) * 100,
      }));
      return {
        label: s.strategy_name,
        color: SERIES_COLORS[i % SERIES_COLORS.length],
        points: normalized,
        pctReturn: true,
      };
    });
  }, [completed]);

  const metricRows = useMemo(() => {
    const rows: {
      label: string;
      values: (string | number | null)[];
      lowerIsBetter?: boolean;
    }[] = [
      {
        label: "Net P&L (₹)",
        values: completed.map((s) => s.summary?.net_pnl ?? null),
      },
      {
        label: "Return %",
        values: completed.map((s) =>
          s.summary?.return_pct != null
            ? `${s.summary.return_pct >= 0 ? "+" : ""}${s.summary.return_pct.toFixed(2)}%`
            : null,
        ),
      },
      {
        label: "Win Rate %",
        values: completed.map((s) =>
          s.summary?.win_rate != null ? `${s.summary.win_rate.toFixed(1)}%` : null,
        ),
      },
      {
        label: "Max Drawdown %",
        values: completed.map((s) =>
          s.summary?.max_drawdown_pct != null
            ? `${s.summary.max_drawdown_pct.toFixed(2)}%`
            : null,
        ),
        lowerIsBetter: true,
      },
      {
        label: "Sharpe Ratio",
        values: completed.map((s) =>
          s.summary?.sharpe_ratio != null ? s.summary.sharpe_ratio.toFixed(2) : null,
        ),
      },
      {
        label: "Profit Factor",
        values: completed.map((s) =>
          s.summary?.profit_factor != null ? s.summary.profit_factor.toFixed(2) : null,
        ),
      },
      {
        label: "Total Trades",
        values: completed.map((s) => s.summary?.total_trades ?? null),
      },
    ];
    if (result && selected.length >= 2) {
      rows.push({
        label: "Combined P&L (₹)",
        values: [
          result.total_pnl,
          ...Array(selected.length - 1).fill(null),
        ],
      });
    }
    return rows;
  }, [completed, result, selected.length]);

  async function runCompare() {
    if (selected.length < 2) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api<PortfolioBacktestOut>("/portfolio/backtest", {
        method: "POST",
        body: JSON.stringify({
          strategy_ids: selected,
          start,
          end,
          initial_capital: Number(capital) || 1000000,
          costs_pct: Number(costs) || 0.05,
        }),
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Compare failed");
    } finally {
      setRunning(false);
    }
  }

  function selectStrategy(idx: number, id: string) {
    setSelected((cur) => {
      const next = [...cur];
      next[idx] = id;
      return next.filter(Boolean);
    });
  }

  const usable = strategies.filter((s) => s.definition !== null);
  const headers = selected.map(
    (id) => usable.find((s) => s.id === id)?.name ?? id.slice(0, 8),
  );

  return (
    <div className="space-y-5">
      <Card title="Strategy Comparison">
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <label key={i} className="block text-xs font-medium text-slate-500">
                Strategy {i + 1}
                <select
                  value={selected[i] ?? ""}
                  onChange={(e) => selectStrategy(i, e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
                >
                  <option value="">—</option>
                  {usable.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-slate-500">From</label>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              />
              <label className="text-xs font-medium text-slate-500">To</label>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              />
            </div>
            <button
              onClick={runCompare}
              disabled={running || selected.length < 2}
              className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
            >
              {running ? "Comparing…" : "Compare"}
            </button>
            {selected.length > 0 && (
              <button
                onClick={() => setSelected([])}
                className="text-xs text-slate-400 underline hover:no-underline"
              >
                Clear all
              </button>
            )}
          </div>
        </div>

        {error && (
          <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
            {error}
          </p>
        )}
      </Card>

      {series.length > 0 && (
        <>
          <Card title="Equity Curves (normalized to % return)">
            <EquityCurveChart
              series={series}
              height={280}
              showLegend={true}
            />
          </Card>

          <Card title="Metrics Comparison">
            <MetricCompareTable
              rows={metricRows}
              headers={headers}
              highlightBest={true}
            />
          </Card>
        </>
      )}
    </div>
  );
}
