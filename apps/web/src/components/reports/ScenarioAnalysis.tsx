"use client";

import { useState } from "react";
import {
  api,
  type BasketLeg,
  type ScenarioResponse,
  type ScenarioResult,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

const COLORS = [
  "#059669", // emerald
  "#dc2626", // red
  "#2563eb", // blue
  "#d97706", // amber
  "#7c3aed", // violet
  "#0891b2", // cyan
  "#db2777", // pink
  "#65a30d", // lime
  "#9333ea", // purple
];

const PRESETS = [
  { name: "Down 3%", spot_offset_pct: -3, iv_offset_pts: 0, dte_offset_days: 0 },
  { name: "Up 3%", spot_offset_pct: 3, iv_offset_pts: 0, dte_offset_days: 0 },
  { name: "IV +8", spot_offset_pct: 0, iv_offset_pts: 8, dte_offset_days: 0 },
  { name: "IV -8", spot_offset_pct: 0, iv_offset_pts: -8, dte_offset_days: 0 },
  { name: "1 day to expiry", spot_offset_pct: 0, iv_offset_pts: 0, dte_offset_days: -999 },
  { name: "Vol crush + move", spot_offset_pct: 2, iv_offset_pts: -6, dte_offset_days: -2 },
];

function fmtMoney(v: number | null): string {
  if (v === null) return "∞";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  return `${sign}₹${abs.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function MiniSparkline({ points, color }: { points: { expiry_value: number }[]; color: string }) {
  const w = 220, h = 48, pad = 4;
  const ys = points.map((p) => p.expiry_value);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const span = max - min || 1;
  const zeroY = h - pad - ((0 - min) / span) * (h - 2 * pad);
  const path = points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"} ${(pad + (i / (points.length - 1)) * (w - 2 * pad)).toFixed(1)} ${(
          h -
          pad -
          ((p.expiry_value - min) / span) * (h - 2 * pad)
        ).toFixed(1)}`,
    )
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      <line x1={pad} y1={zeroY} x2={w - pad} y2={zeroY} stroke="#cbd5e1" strokeDasharray="3 3" />
      <path d={path} fill="none" stroke={color} strokeWidth={1.8} />
    </svg>
  );
}

function ScenarioCard({
  result,
  base,
  color,
}: {
  result: ScenarioResult;
  base: ScenarioResult;
  color: string;
}) {
  const thetaDelta = result.combined_theta - base.combined_theta;
  const vegaDelta = result.combined_vega - base.combined_vega;
  const premiumDelta = result.net_premium - base.net_premium;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-[13px] font-semibold text-slate-900">{result.name}</h4>
        <span className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
      </div>
      <p className="mt-0.5 text-[11px] text-slate-400">
        Spot {result.spot.toLocaleString("en-IN")} · {result.days_to_expiry}d · IV {result.volatility}%
      </p>
      <MiniSparkline points={result.payoff} color={color} />
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <p className="text-slate-400">Max profit</p>
          <p className="font-semibold text-emerald-600 tabular-nums">{fmtMoney(result.max_profit)}</p>
        </div>
        <div>
          <p className="text-slate-400">Max loss</p>
          <p className="font-semibold text-red-600 tabular-nums">{fmtMoney(result.max_loss)}</p>
        </div>
      </div>
      <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 text-[11px]">
        <div className="flex justify-between">
          <span className="text-slate-400">Net premium</span>
          <span className={`tabular-nums ${premiumDelta === 0 ? "text-slate-600" : premiumDelta > 0 ? "text-emerald-600" : "text-red-600"}`}>
            {fmtMoney(result.net_premium)}
            {premiumDelta !== 0 && <span className="text-slate-400"> ({premiumDelta > 0 ? "+" : ""}{fmtMoney(premiumDelta)})</span>}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Theta/day</span>
          <span className={`tabular-nums ${thetaDelta === 0 ? "text-slate-600" : thetaDelta > 0 ? "text-emerald-600" : "text-red-600"}`}>
            {result.combined_theta.toFixed(2)}
            {thetaDelta !== 0 && <span className="text-slate-400"> ({thetaDelta > 0 ? "+" : ""}{thetaDelta.toFixed(2)})</span>}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Vega</span>
          <span className={`tabular-nums ${vegaDelta === 0 ? "text-slate-600" : vegaDelta > 0 ? "text-emerald-600" : "text-red-600"}`}>
            {result.combined_vega.toFixed(2)}
            {vegaDelta !== 0 && <span className="text-slate-400"> ({vegaDelta > 0 ? "+" : ""}{vegaDelta.toFixed(2)})</span>}
          </span>
        </div>
      </div>
    </div>
  );
}

interface ScenarioAnalysisProps {
  spot: number;
  dte: number;
  vol: number;
  legs: BasketLeg[];
}

export function ScenarioAnalysis({ spot, dte, vol, legs }: ScenarioAnalysisProps) {
  const [scenarios, setScenarios] = useState([...PRESETS.slice(0, 3)]);
  const [result, setResult] = useState<ScenarioResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function togglePreset(p: (typeof PRESETS)[number]) {
    setScenarios((prev) => {
      const exists = prev.some((s) => s.name === p.name);
      if (exists) return prev.filter((s) => s.name !== p.name);
      if (prev.length >= 8) return prev;
      return [...prev, { ...p }];
    });
  }

  async function analyze() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const resp = await api<ScenarioResponse>("/basket/scenario", {
        method: "POST",
        body: JSON.stringify({
          spot,
          days_to_expiry: dte,
          volatility: vol,
          legs: legs.map((l) => ({
            action: l.action,
            option_type: l.option_type,
            strike: l.strike,
            premium: l.premium,
            quantity: l.quantity,
          })),
          scenarios,
        }),
      });
      setResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scenario analysis failed");
    } finally {
      setBusy(false);
    }
  }

  const allResults = result ? [result.base, ...result.scenarios] : [];

  return (
    <div className="space-y-4">
      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}
      <Card
        title="Scenario Analysis"
        subtitle="Reprice the basket under Spot / IV / DTE offsets — mirrors AlgoTest"
      >
        <div className="mb-3 flex flex-wrap gap-2">
          {PRESETS.map((p) => {
            const active = scenarios.some((s) => s.name === p.name);
            return (
              <button
                key={p.name}
                onClick={() => togglePreset(p)}
                className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
                  active
                    ? "border-blue-300 bg-blue-50 text-blue-700"
                    : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                }`}
              >
                {p.name}
              </button>
            );
          })}
        </div>
        <p className="mb-3 text-[11px] text-slate-400">
          Uses the same basket inputs from the Basket Payoff tab: spot {spot.toLocaleString("en-IN")} · {dte} DTE · IV {vol}%.
        </p>
        <div className="flex items-center gap-3">
          <button
            onClick={analyze}
            disabled={busy || legs.length === 0 || scenarios.length === 0}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? "Analyzing…" : `Analyze ${scenarios.length} scenario${scenarios.length === 1 ? "" : "s"}`}
          </button>
          {result && <Badge tone="blue">{result.scenarios.length} scenarios vs base</Badge>}
        </div>
      </Card>

      {result && (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            <ScenarioCard result={result.base} base={result.base} color={COLORS[0]} />
            {result.scenarios.map((s, i) => (
              <ScenarioCard key={s.name} result={s} base={result.base} color={COLORS[(i + 1) % COLORS.length]} />
            ))}
          </div>

          <Card title="Expiry P&L comparison" subtitle="Base and each scenario overlaid on one chart">
            <ComparisonChart results={allResults} />
          </Card>
        </>
      )}
    </div>
  );
}

function ComparisonChart({ results }: { results: ScenarioResult[] }) {
  const W = 780, H = 320;
  const PAD = { l: 64, r: 18, t: 14, b: 36 };
  const allXs = results.flatMap((r) => r.payoff.map((p) => p.underlying));
  const xmin = Math.min(...allXs), xmax = Math.max(...allXs);
  let ymin = Infinity, ymax = -Infinity;
  for (const r of results) for (const p of r.payoff) {
    if (p.expiry_value < ymin) ymin = p.expiry_value;
    if (p.expiry_value > ymax) ymax = p.expiry_value;
  }
  const span = Math.max((ymax - ymin) * 0.1, 1);
  ymin -= span; ymax += span;
  const X = (v: number) => PAD.l + ((v - xmin) / (xmax - xmin || 1)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + ((ymax - v) / (ymax - ymin || 1)) * (H - PAD.t - PAD.b);
  const zeroY = Y(0);

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <line x1={PAD.l} y1={zeroY} x2={W - PAD.r} y2={zeroY} stroke="#94a3b8" strokeDasharray="4 3" />
        {results.map((r, i) => {
          const color = COLORS[i % COLORS.length];
          const path = r.payoff
            .map((p, j) => `${j === 0 ? "M" : "L"} ${X(p.underlying).toFixed(1)} ${Y(p.expiry_value).toFixed(1)}`)
            .join(" ");
          return (
            <path
              key={r.name}
              d={path}
              fill="none"
              stroke={color}
              strokeWidth={i === 0 ? 2.4 : 1.6}
              strokeDasharray={i === 0 ? "none" : "5 4"}
              opacity={i === 0 ? 1 : 0.85}
            />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-500">
        {results.map((r, i) => (
          <span key={r.name} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-4"
              style={{ background: COLORS[i % COLORS.length] }}
            />
            {r.name}
          </span>
        ))}
      </div>
    </div>
  );
}
