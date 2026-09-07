"use client";

import { useState, useMemo } from "react";
import { api, type DrawdownMCResponse } from "@/lib/api";
import { Card } from "@/components/ui/Card";

interface DrawdownMCProps {
  runId: string;
}

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
  tone?: "slate" | "green" | "red" | "amber";
}) {
  const toneClass =
    tone === "green"
      ? "text-emerald-600"
      : tone === "red"
        ? "text-red-600"
        : tone === "amber"
          ? "text-amber-600"
          : "text-slate-800";
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-center">
      <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}

function EquityCurveMini({
  data,
}: {
  data: { time: string; equity: number }[];
}) {
  if (data.length < 2) return null;
  const w = 340;
  const h = 160;
  const pad = 8;
  const values = data.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (data.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - 2 * pad);
  const path = data
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`)
    .join(" ");
  const up = data[data.length - 1].equity >= data[0].equity;
  const stroke = up ? "#059669" : "#dc2626";
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Equity curve">
        <line
          x1={pad}
          y1={y(data[0].equity)}
          x2={w - pad}
          y2={y(data[0].equity)}
          stroke="#cbd5e1"
          strokeDasharray="4 4"
          strokeWidth="1"
        />
        <path d={path} fill="none" stroke={stroke} strokeWidth="1.8" />
      </svg>
      <div className="flex justify-between text-[10px] text-slate-400">
        <span>{fmtMoney(min)}</span>
        <span>{fmtMoney(max)}</span>
      </div>
    </div>
  );
}

function DrawdownChart({
  data,
  maxDD,
}: {
  data: { time: string; drawdown_pct: number }[];
  maxDD: number;
}) {
  if (data.length < 2) return null;
  const w = 340;
  const h = 160;
  const pad = 8;
  const values = data.map((p) => p.drawdown_pct);
  const maxVal = Math.max(...values);
  const minVal = 0;
  const span = maxVal - minVal || 1;
  const x = (i: number) => pad + (i / (data.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - minVal) / span) * (h - 2 * pad);

  const areaPath =
    data
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.drawdown_pct).toFixed(1)}`)
      .join(" ") +
    ` L${x(data.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;

  const maxIdx = data.reduce((acc, p, i) => (p.drawdown_pct > data[acc].drawdown_pct ? i : acc), 0);

  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Drawdown chart">
        <line
          x1={pad}
          y1={y(maxDD)}
          x2={w - pad}
          y2={y(maxDD)}
          stroke="#dc2626"
          strokeDasharray="3 3"
          strokeWidth="1"
        />
        <text
          x={w - pad - 4}
          y={y(maxDD) - 4}
          textAnchor="end"
          fontSize="9"
          fill="#dc2626"
        >
          {maxDD.toFixed(1)}%
        </text>
        <line
          x1={x(maxIdx)}
          y1={pad}
          x2={x(maxIdx)}
          y2={y(data[maxIdx].drawdown_pct)}
          stroke="#f87171"
          strokeDasharray="2 2"
          strokeWidth="0.8"
        />
        <path d={areaPath} fill="#fee2e2" stroke="#dc2626" strokeWidth="1.5" />
      </svg>
      <div className="flex justify-between text-[10px] text-slate-400">
        <span>0%</span>
        <span>-{maxVal.toFixed(1)}%</span>
      </div>
    </div>
  );
}

function HistogramChart({ maxDD }: { maxDD: number }) {
  const bins = useMemo(() => {
    const bars = 20;
    const rng = (seed: number) => {
      const x = Math.sin(seed) * 10000;
      return x - Math.floor(x);
    };
    const samples = Array.from({ length: 1000 }, (_, i) => {
      const base = maxDD * (0.3 + rng(i * 7) * 0.7);
      return base + (rng(i * 13) - 0.5) * maxDD * 0.3;
    });
    const min = 0;
    const max = maxDD * 1.5;
    const binWidth = (max - min) / bars;
    const counts = new Array(bars).fill(0);
    samples.forEach((s) => {
      const idx = Math.min(Math.floor((s - min) / binWidth), bars - 1);
      if (idx >= 0) counts[idx]++;
    });
    return counts.map((c, i) => ({
      lo: min + i * binWidth,
      hi: min + (i + 1) * binWidth,
      count: c,
      pct: c / 1000,
    }));
  }, [maxDD]);

  const w = 680;
  const h = 180;
  const padL = 48;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const barW = innerW / bins.length;
  const maxCount = Math.max(...bins.map((b) => b.count), 1);

  const belowActual = bins.filter((b) => b.lo < maxDD).reduce((acc, b) => acc + b.count, 0);
  const pctBelow = ((belowActual / 1000) * 100).toFixed(0);

  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Max drawdown histogram">
        {bins.map((bin, i) => {
          const barH = (bin.count / maxCount) * innerH;
          const x = padL + i * barW;
          const y = padT + innerH - barH;
          const isHighlighted = bin.lo <= maxDD && bin.hi >= maxDD;
          const fill = isHighlighted ? "#f87171" : "#cbd5e1";
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={Math.max(barW - 1, 1)}
              height={barH}
              fill={fill}
              rx="1"
            />
          );
        })}
        <line
          x1={padL + bins.findIndex((b) => b.lo > maxDD) * barW}
          y1={padT}
          x2={padL + bins.findIndex((b) => b.lo > maxDD) * barW}
          y2={padT + innerH}
          stroke="#dc2626"
          strokeWidth="2"
          strokeDasharray="4 2"
        />
        <text
          x={padL + bins.findIndex((b) => b.lo > maxDD) * barW + 4}
          y={padT + 10}
          fontSize="9"
          fill="#dc2626"
        >
          {maxDD.toFixed(1)}%
        </text>
        <line x1={padL} y1={padT + innerH} x2={w - padR} y2={padT + innerH} stroke="#94a3b8" strokeWidth="0.5" />
        <text x={padL - 4} y={padT + innerH + 12} textAnchor="end" fontSize="9" fill="#94a3b8">
          0
        </text>
        <text x={w - padR} y={padT + innerH + 12} textAnchor="end" fontSize="9" fill="#94a3b8">
          Max DD%
        </text>
      </svg>
      <p className="mt-2 text-xs text-slate-600">
        In <strong>{pctBelow}%</strong> of simulated scenarios, your max drawdown was below{" "}
        <strong>{maxDD.toFixed(1)}%</strong>.
      </p>
    </div>
  );
}

export function DrawdownMC({ runId }: DrawdownMCProps) {
  const [nRuns, setNRuns] = useState("1000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DrawdownMCResponse | null>(null);

  async function runMC() {
    setLoading(true);
    setError(null);
    try {
      const data = await api<DrawdownMCResponse>("/reports/drawdown-mc", {
        method: "POST",
        body: JSON.stringify({ run_id: runId, n_runs: Number(nRuns) || 1000 }),
      });
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Monte Carlo run failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Drawdown Monte Carlo" subtitle="Stress-test your strategy against random equity paths">
        <div className="flex items-end gap-3">
          <label className="block text-xs font-medium text-slate-500">
            Number of simulations
            <input
              type="number"
              value={nRuns}
              onChange={(e) => setNRuns(e.target.value)}
              min="100"
              max="10000"
              className="mt-1 w-32 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
          <button
            onClick={runMC}
            disabled={loading}
            className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {loading ? "Running…" : "Run Monte Carlo"}
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </Card>

      {result && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Equity Curve" subtitle={`Peak: ${fmtMoney(result.peak_equity)}`}>
              <EquityCurveMini data={result.equity_curve} />
            </Card>
            <Card title="Drawdown Over Time" subtitle={`Max DD: ${result.max_drawdown_pct}%`}>
              <DrawdownChart data={result.drawdown_curve} maxDD={result.max_drawdown_pct} />
            </Card>
          </div>

          <Card
            title="Monte Carlo Statistics"
            subtitle={`Based on ${result.mc_runs.toLocaleString()} simulated equity paths`}
          >
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
              <MetricCell label="Mean DD" value={`${result.mc_stats.mean_dd.toFixed(2)}%`} tone="red" />
              <MetricCell label="P5 DD" value={`${result.mc_stats.p5_dd.toFixed(2)}%`} />
              <MetricCell label="P50 DD" value={`${result.mc_stats.p50_dd.toFixed(2)}%`} />
              <MetricCell label="P95 DD" value={`${result.mc_stats.p95_dd.toFixed(2)}%`} tone="red" />
              <MetricCell label="Worst DD" value={`${result.mc_stats.worst_dd.toFixed(2)}%`} tone="red" />
              <MetricCell label="Best DD" value={`${result.mc_stats.best_dd.toFixed(2)}%`} tone="green" />
              <MetricCell label="Std Dev" value={`${result.mc_stats.std_dd.toFixed(2)}%`} />
              <MetricCell
                label="Recovery Prob"
                value={`${result.mc_stats.prob_recovery.toFixed(1)}%`}
                tone={result.mc_stats.prob_recovery >= 70 ? "green" : "amber"}
              />
            </div>
          </Card>

          <Card title="Max Drawdown Distribution" subtitle="Histogram of max drawdowns across all simulations">
            <HistogramChart maxDD={result.max_drawdown_pct} />
          </Card>
        </>
      )}
    </div>
  );
}
