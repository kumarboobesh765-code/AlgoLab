"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { api, type DailyPnlResponse, type Strategy } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { downloadCsv } from "@/lib/csv";

function fmtMoney(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function MetricCell({
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

function todayISO(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function DailyPnlBarChart({ data }: { data: { date: string; pnl: number; cumulative: number }[] }) {
  if (data.length < 2) return null;
  const w = 760;
  const h = 220;
  const padL = 56;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const pnls = data.map((d) => d.pnl);
  const maxAbs = Math.max(...pnls.map((v) => Math.abs(v)), 1);
  const yMin = -maxAbs;
  const yMax = maxAbs;
  const ySpan = yMax - yMin;

  const x = (i: number) => padL + (i / (data.length - 1)) * innerW;
  const y = (v: number) => padT + (1 - (v - yMin) / ySpan) * innerH;
  const zeroY = y(0);
  const barW = (innerW / data.length) * 0.7;

  const yTicks = 5;
  const tickValues = Array.from({ length: yTicks + 1 }, (_, i) => yMin + (ySpan * i) / yTicks);

  const cumMin = Math.min(...data.map((p) => p.cumulative), 0);
  const cumMax = Math.max(...data.map((p) => p.cumulative), 0);
  const cumSpan = cumMax - cumMin || 1;
  const cumY = (v: number) => padT + (1 - (v - cumMin) / cumSpan) * innerH;
  const cumPathScaled = data
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${cumY(p.cumulative).toFixed(1)}`)
    .join(" ");

  const xTickIdx = [0, Math.floor((data.length - 1) / 2), data.length - 1];

  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Daily P&L chart">
        {tickValues.map((tv, i) => (
          <g key={`y-${i}`}>
            <line
              x1={padL}
              y1={y(tv)}
              x2={w - padR}
              y2={y(tv)}
              stroke="#f1f5f9"
              strokeWidth="0.5"
            />
            <text
              x={padL - 6}
              y={y(tv) + 3}
              textAnchor="end"
              fontSize="9"
              fill="#94a3b8"
            >
              {fmtMoney(tv)}
            </text>
          </g>
        ))}

        <line
          x1={padL}
          y1={zeroY}
          x2={w - padR}
          y2={zeroY}
          stroke="#cbd5e1"
          strokeDasharray="3 3"
          strokeWidth="0.8"
        />

        {data.map((d, i) => {
          const barY = d.pnl >= 0 ? y(d.pnl) : zeroY;
          const barH = Math.abs(y(d.pnl) - zeroY);
          const fill = d.pnl >= 0 ? "#10b981" : "#ef4444";
          return (
            <rect
              key={i}
              x={x(i) - barW / 2}
              y={barY}
              width={barW}
              height={barH}
              fill={fill}
              rx="1"
            />
          );
        })}

        <path d={cumPathScaled} fill="none" stroke="#7c3aed" strokeWidth="1.8" />

        {xTickIdx.map((i) => {
          if (i >= data.length) return null;
          return (
            <text
              key={`x-${i}`}
              x={x(i)}
              y={h - 8}
              textAnchor="middle"
              fontSize="10"
              fill="#94a3b8"
            >
              {data[i].date}
            </text>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-600">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 rounded-sm bg-emerald-500" /> Profit day
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 rounded-sm bg-red-500" /> Loss day
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 bg-violet-500" /> Cumulative
        </span>
        <span className="ml-auto text-slate-500">
          Cum range: {fmtMoney(cumMin)} → {fmtMoney(cumMax)}
        </span>
      </div>
    </div>
  );
}

export default function DailyPnlPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [start, setStart] = useState(todayISO(-30));
  const [end, setEnd] = useState(todayISO(-1));
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<DailyPnlResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Strategy[]>("/strategies")
      .then((all) => setStrategies(all))
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load strategies"),
      );
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      if (selected.length > 0) params.set("strategy_ids", selected.join(","));
      const res = await api<DailyPnlResponse>(`/reports/daily-pnl?${params.toString()}`);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load daily P&L");
    } finally {
      setLoading(false);
    }
  }, [start, end, selected]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
  }, [loadData]);

  const bestDay = useMemo(() => {
    if (!data || data.points.length === 0) return null;
    return data.points.reduce((acc, p) => (p.pnl > acc.pnl ? p : acc), data.points[0]);
  }, [data]);

  const worstDay = useMemo(() => {
    if (!data || data.points.length === 0) return null;
    return data.points.reduce((acc, p) => (p.pnl < acc.pnl ? p : acc), data.points[0]);
  }, [data]);

  function toggleStrategy(id: string) {
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

  function exportCsv() {
    if (!data) return;
    downloadCsv(
      "daily_pnl.csv",
      ["date", "pnl", "cumulative", "winning"],
      data.points.map((p) => [p.date, p.pnl, p.cumulative, p.pnl > 0 ? "yes" : "no"]),
    );
  }

  return (
    <div className="space-y-4">
      <Card
        title="Daily P&L Analysis"
        subtitle="Aggregated P&L per trading day across all completed backtest runs."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
              Strategies
            </p>
            <div className="mt-2 max-h-32 space-y-1 overflow-y-auto rounded-md border border-slate-200 bg-white p-2 text-xs">
              {strategies.length === 0 ? (
                <p className="text-slate-400">No strategies yet</p>
              ) : (
                strategies.map((s) => (
                  <label
                    key={s.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(s.id)}
                      onChange={() => toggleStrategy(s.id)}
                      className="rounded border-slate-300"
                    />
                    <span className="text-slate-700">{s.name}</span>
                    <span className="ml-auto text-[10px] text-slate-400">v{s.current_version}</span>
                  </label>
                ))
              )}
            </div>
            <p className="mt-1 text-[10px] text-slate-400">
              {selected.length === 0 ? "All strategies" : `${selected.length} selected`}
            </p>
          </div>
          <label className="block text-xs font-medium text-slate-500">
            Start date
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            End date
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
          <div className="flex items-end">
            <button
              onClick={loadData}
              disabled={loading}
              className="w-full rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
            >
              {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>
      </Card>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}

      {data && (
        <>
          <Card title="Summary">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <MetricCell
                label="Total P&L"
                value={`${data.total_pnl >= 0 ? "+" : ""}${fmtMoney(data.total_pnl)}`}
                tone={data.total_pnl >= 0 ? "green" : "red"}
              />
              <MetricCell label="Total Trades" value={`${data.total_trades}`} />
              <MetricCell
                label="Winning Days"
                value={`${data.winning_days}`}
                tone="green"
              />
              <MetricCell
                label="Losing Days"
                value={`${data.losing_days}`}
                tone="red"
              />
              <MetricCell
                label="Best Day"
                value={bestDay ? `+${fmtMoney(bestDay.pnl)}` : "—"}
                tone="green"
              />
              <MetricCell
                label="Worst Day"
                value={worstDay ? fmtMoney(worstDay.pnl) : "—"}
                tone="red"
              />
            </div>
          </Card>

          <Card
            title="Daily P&L"
            subtitle={`${data.points.length} trading day${data.points.length === 1 ? "" : "s"}`}
            actions={
              <button
                onClick={exportCsv}
                className="rounded border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
              >
                Export CSV
              </button>
            }
          >
            {data.points.length === 0 ? (
              <p className="text-xs text-slate-500">No daily P&L data in this range.</p>
            ) : (
              <DailyPnlBarChart data={data.points} />
            )}
          </Card>

          <Card title="Daily P&L Table">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-slate-400">
                  <tr>
                    <th className="py-1 pr-3">Date</th>
                    <th className="py-1 pr-3">P&L</th>
                    <th className="py-1 pr-3">Cumulative</th>
                    <th className="py-1 pr-3"># Trades</th>
                    <th className="py-1">Winning Day</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {data.points.map((p) => (
                    <tr key={p.date} className="border-t border-slate-100">
                      <td className="py-1 pr-3 text-slate-700">{p.date}</td>
                      <td
                        className={`py-1 pr-3 font-medium ${p.pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}
                      >
                        {p.pnl >= 0 ? "+" : ""}
                        {fmtMoney(p.pnl)}
                      </td>
                      <td
                        className={`py-1 pr-3 ${p.cumulative >= 0 ? "text-emerald-700" : "text-red-700"}`}
                      >
                        {fmtMoney(p.cumulative)}
                      </td>
                      <td className="py-1 pr-3 text-slate-500">
                        {data.total_trades > 0
                          ? Math.max(1, Math.round(data.total_trades / data.points.length))
                          : 0}
                      </td>
                      <td className="py-1">
                        {p.pnl > 0 ? (
                          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700 ring-1 ring-emerald-200">
                            Yes
                          </span>
                        ) : p.pnl < 0 ? (
                          <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] text-red-700 ring-1 ring-red-200">
                            No
                          </span>
                        ) : (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 ring-1 ring-slate-200">
                            Flat
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
