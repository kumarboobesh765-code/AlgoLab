"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Instrument,
  type MonteCarloBin,
  type MonteCarloResponse,
  type OptionChain,
  type PayoffResponse,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";
import { PayoffChart, inr, fmt } from "@/components/charts/PayoffChart";

interface MarginEstimate {
  lot_size: number;
  spot_used: number;
  legs: Array<{
    label: string;
    span: number;
    exposure: number;
    premium_paid: number;
    total: number;
  }>;
  hedge_discount: number;
  total_margin: number;
  premium_outlay: number;
  defined_risk: boolean;
  max_loss_theoretical: number | null;
  disclaimer?: string;
}

const UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"];
const STRIKE_STEPS: Record<string, number> = {
  NIFTY: 50,
  BANKNIFTY: 100,
  FINNIFTY: 50,
  MIDCPNIFTY: 75,
  SENSEX: 100,
};

interface LegState {
  id: number;
  action: "buy" | "sell";
  option_type: "CE" | "PE";
  offset: number;
  lots: number;
}

let legSeq = 1;
function mkLeg(action: "buy" | "sell", option_type: "CE" | "PE", offset: number): LegState {
  return { id: legSeq++, action, option_type, offset, lots: 1 };
}

function Histogram({ bins }: { bins: MonteCarloBin[] }) {
  const max = Math.max(...bins.map((b) => b.count), 1);
  return (
    <div className="flex h-28 items-end gap-px">
      {bins.map((b) => {
        const mid = (b.lo + b.hi) / 2;
        return (
          <div
            key={b.lo}
            title={`${fmt(b.lo, 0)} to ${fmt(b.hi, 0)}: ${b.count} paths`}
            className={`flex-1 rounded-t-sm ${mid >= 0 ? "bg-emerald-500/70" : "bg-red-400/70"}`}
            style={{ height: `${Math.max((b.count / max) * 100, b.count > 0 ? 3 : 0)}%` }}
          />
        );
      })}
    </div>
  );
}

export default function PayoffLabPage() {
  const [underlying, setUnderlying] = useState("NIFTY");
  const [expiries, setExpiries] = useState<string[]>([]);
  const [expiry, setExpiry] = useState<string>("");
  const [dte, setDte] = useState(7);
  const [lotSizes, setLotSizes] = useState<Record<string, number>>({});
  const [legs, setLegs] = useState<LegState[]>([mkLeg("buy", "CE", 0), mkLeg("buy", "PE", 0)]);
  const [result, setResult] = useState<PayoffResponse | null>(null);
  const [mc, setMc] = useState<MonteCarloResponse | null>(null);
  const [paths, setPaths] = useState(10000);
  const [busy, setBusy] = useState(false);
  const [mcBusy, setMcBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [margin, setMargin] = useState<MarginEstimate | null>(null);
  const [marginBusy, setMarginBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<Instrument[]>("/market/instruments")
      .then((list) => {
        if (!cancelled) {
          setLotSizes(Object.fromEntries(list.map((i) => [i.symbol.toUpperCase(), i.lot_size])));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api<OptionChain>(`/market/option-chain?underlying=${underlying}`)
      .then((c) => {
        if (!cancelled) {
          setExpiries(c.expiries);
          setExpiry(c.expiry);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [underlying]);

  const step = STRIKE_STEPS[underlying] ?? 50;
  const lotSize = lotSizes[underlying] ?? 25;

  const patchLeg = (id: number, patch: Partial<Omit<LegState, "id">>) =>
    setLegs((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLeg = (id: number) => setLegs((prev) => prev.filter((l) => l.id !== id));

  const applyPreset = (name: string) => {
    const w = step * 4;
    const spreads: Record<string, LegState[]> = {
      "Long Straddle": [mkLeg("buy", "CE", 0), mkLeg("buy", "PE", 0)],
      "Short Straddle": [mkLeg("sell", "CE", 0), mkLeg("sell", "PE", 0)],
      "Iron Fly": [
        mkLeg("sell", "CE", 0),
        mkLeg("sell", "PE", 0),
        mkLeg("buy", "CE", w),
        mkLeg("buy", "PE", -w),
      ],
      "Bull Call Spread": [mkLeg("buy", "CE", 0), mkLeg("sell", "CE", step * 6)],
      "Bear Put Spread": [mkLeg("buy", "PE", 0), mkLeg("sell", "PE", -step * 6)],
    };
    setLegs(spreads[name]);
    setResult(null);
    setMc(null);
  };

  const requestBody = () => ({
    underlying,
    expiry,
    dte_days: dte,
    lot_size: lotSize,
    legs: legs.map((l) => ({
      action: l.action,
      option_type: l.option_type,
      strike_offset: l.offset,
      lots: l.lots,
    })),
  });

  const analyze = () => {
    setBusy(true);
    setError(null);
    api<PayoffResponse>("/options/payoff", { method: "POST", body: JSON.stringify(requestBody()) })
      .then((r) => {
        setResult(r);
        setMc(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Payoff analysis failed"))
      .finally(() => setBusy(false));
  };

  const runMonteCarlo = () => {
    setMcBusy(true);
    setError(null);
    api<MonteCarloResponse>("/options/monte-carlo", {
      method: "POST",
      body: JSON.stringify({ ...requestBody(), paths }),
    })
      .then(setMc)
      .catch((e) => setError(e instanceof Error ? e.message : "Simulation failed"))
      .finally(() => setMcBusy(false));
  };

  const calculateMargin = async () => {
    setMarginBusy(true);
    setError(null);
    try {
      const resp = await api("/options/margin", {
        method: "POST",
        body: JSON.stringify({
          underlying,
          expiry,
          dte_days: dte,
          lot_size: lotSize,
          spot: result?.spot,
          legs: legs.map((l) => ({
            action: l.action,
            option_type: l.option_type,
            strike_offset: l.offset,
            lots: l.lots,
          })),
        }),
      });
      setMargin(resp as MarginEstimate);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Margin calculation failed");
    } finally {
      setMarginBusy(false);
    }
  };

  const presetNames = useMemo(
    () => ["Long Straddle", "Short Straddle", "Iron Fly", "Bull Call Spread", "Bear Put Spread"],
    [],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {UNDERLYINGS.map((u) => (
            <button
              key={u}
              onClick={() => {
                setUnderlying(u);
                setResult(null);
                setMc(null);
              }}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                u === underlying
                  ? "bg-blue-600 text-white"
                  : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {u}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>
            Lot size <strong className="text-slate-700">{lotSize}</strong>
          </span>
          <label className="flex items-center gap-1">
            Expiry
            <select
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-800"
            >
              {expiries.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            DTE
            <input
              type="number"
              value={dte}
              min="0"
              max="365"
              onChange={(e) => setDte(Number(e.target.value))}
              className="w-16 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-800"
            />
          </label>
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}

      <Card
        title="Strategy Legs"
        subtitle="Strikes are relative to ATM · premiums resolve live from the option chain"
        actions={
          <button
            onClick={() => setLegs((prev) => [...prev, mkLeg("buy", "CE", 0)])}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            + Add Leg
          </button>
        }
      >
        <div className="mb-3 flex flex-wrap gap-2">
          {presetNames.map((p) => (
            <button
              key={p}
              onClick={() => applyPreset(p)}
              className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-[11px] font-medium text-blue-700 hover:bg-blue-100"
            >
              {p}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {legs.map((leg) => (
            <div key={leg.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-100 px-3 py-2">
              <button
                onClick={() => patchLeg(leg.id, { action: leg.action === "buy" ? "sell" : "buy" })}
                className={`w-14 rounded-md px-2 py-1 text-xs font-semibold ${
                  leg.action === "buy" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                }`}
              >
                {leg.action === "buy" ? "BUY" : "SELL"}
              </button>
              <button
                onClick={() => patchLeg(leg.id, { option_type: leg.option_type === "CE" ? "PE" : "CE" })}
                className={`w-12 rounded-md px-2 py-1 text-xs font-semibold ${
                  leg.option_type === "CE" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"
                }`}
              >
                {leg.option_type}
              </button>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => patchLeg(leg.id, { offset: leg.offset - step })}
                  className="h-6 w-6 rounded border border-slate-200 text-xs text-slate-500 hover:bg-slate-50"
                >
                  −
                </button>
                <span className="w-20 text-center text-xs font-medium tabular-nums text-slate-700">
                  {leg.offset >= 0 ? `+${leg.offset}` : leg.offset}
                </span>
                <button
                  onClick={() => patchLeg(leg.id, { offset: leg.offset + step })}
                  className="h-6 w-6 rounded border border-slate-200 text-xs text-slate-500 hover:bg-slate-50"
                >
                  +
                </button>
              </div>
              <label className="ml-auto flex items-center gap-1 text-[11px] text-slate-500">
                lots
                <input
                  type="number"
                  value={leg.lots}
                  min="1"
                  onChange={(e) => patchLeg(leg.id, { lots: Math.max(1, Number(e.target.value)) })}
                  className="w-14 rounded-md border border-slate-300 px-2 py-1 text-sm tabular-nums text-slate-800"
                />
              </label>
              <button
                onClick={() => removeLeg(leg.id)}
                disabled={legs.length <= 1}
                className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-30"
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={analyze}
            disabled={busy || legs.length === 0}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? "Analyzing…" : "Analyze Payoff"}
          </button>
          <button
            onClick={calculateMargin}
            disabled={marginBusy || legs.length === 0 || !result}
            className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {marginBusy ? "Calculating…" : "Calculate Margin"}
          </button>
          {result && result.is_demo && <Badge tone="amber">DEMO DATA — synthetic</Badge>}
        </div>
      </Card>

      {result && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <MetricCard label="Max Profit" value={inr(result.metrics.max_profit)} tone="positive" />
            <MetricCard
              label="Max Loss"
              value={inr(result.metrics.max_loss)}
              tone={result.metrics.max_loss === null ? "negative" : "neutral"}
            />
            <MetricCard
              label="Breakevens"
              value={result.metrics.breakevens.length ? result.metrics.breakevens.map((b) => fmt(b, 0)).join(" / ") : "—"}
            />
            <MetricCard label="Risk : Reward" value={result.metrics.risk_reward !== null ? `1 : ${fmt(result.metrics.risk_reward)}` : "—"} />
            <MetricCard
              label={result.metrics.net_premium <= 0 ? "Net Credit" : "Net Debit"}
              value={inr(Math.abs(result.metrics.net_premium))}
              hint={`${result.legs.length} legs · lot ${result.lot_size}`}
            />
          </div>

          <Card
            title="Expiry Payoff"
            subtitle={`${result.underlying} · spot ${fmt(result.spot)} · ATM ${result.atm_strike.toLocaleString("en-IN")} · expiry ${result.expiry} (${result.dte_days} DTE)`}
          >
            <PayoffChart curve={result.curve} spot={result.spot} breakevens={result.metrics.breakevens} />
          </Card>

          <Card title="Resolved Legs & Greeks">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-[12px] tabular-nums">
                <thead>
                  <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                    <th className="py-1.5 pr-2 font-medium">Action</th>
                    <th className="pr-2 font-medium">Type</th>
                    <th className="pr-2 text-right font-medium">Strike</th>
                    <th className="pr-2 text-right font-medium">Premium</th>
                    <th className="pr-2 text-right font-medium">IV %</th>
                    <th className="pr-2 text-right font-medium">Delta</th>
                    <th className="pr-2 text-right font-medium">Gamma</th>
                    <th className="pr-2 text-right font-medium">Θ/day</th>
                    <th className="text-right font-medium">Vega</th>
                  </tr>
                </thead>
                <tbody>
                  {result.legs.map((leg, i) => (
                    <tr key={i} className="border-b border-slate-50 last:border-0">
                      <td className={`py-1.5 pr-2 font-semibold ${leg.action === "buy" ? "text-emerald-600" : "text-red-600"}`}>
                        {leg.action.toUpperCase()}
                      </td>
                      <td className="pr-2 text-slate-600">{leg.option_type}</td>
                      <td className="pr-2 text-right text-slate-800">{leg.strike.toLocaleString("en-IN")}</td>
                      <td className="pr-2 text-right text-slate-800">{fmt(leg.premium)}</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(leg.iv_pct, 1)}</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(leg.delta)}</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(leg.gamma, 5)}</td>
                      <td className={`pr-2 text-right ${leg.action === "buy" ? "text-red-500" : "text-emerald-600"}`}>
                        {fmt(leg.theta_per_day)}
                      </td>
                      <td className="text-right text-slate-500">{fmt(leg.vega)}</td>
                    </tr>
                  ))}
                  <tr className="font-semibold text-slate-800">
                    <td className="py-1.5 pr-2" colSpan={5}>
                      Net position
                    </td>
                    <td className="pr-2 text-right">{fmt(result.net_greeks.delta)}</td>
                    <td className="pr-2 text-right">{fmt(result.net_greeks.gamma, 5)}</td>
                    <td className={`pr-2 text-right ${result.net_greeks.theta_per_day >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                      {fmt(result.net_greeks.theta_per_day)}
                    </td>
                    <td className="text-right">{fmt(result.net_greeks.vega)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          {margin && (
            <Card title="Margin Estimate (SPAN + Exposure)" subtitle="Rule-of-thumb SPAN + Exposure with hedge discounts — broker's real margin governs">
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-400">Total Margin</p>
                  <p className="mt-0.5 text-sm font-semibold tabular-nums text-emerald-600">{inr(margin.total_margin)}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-400">SPAN</p>
                  <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-800">{inr(margin.legs.reduce((s, l) => s + l.span, 0))}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-400">Exposure</p>
                  <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-800">{inr(margin.legs.reduce((s, l) => s + l.exposure, 0))}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-slate-400">Hedge Discount</p>
                  <p className="mt-0.5 text-sm font-semibold tabular-nums text-emerald-600">{inr(margin.hedge_discount)}</p>
                </div>
              </div>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-[12px] tabular-nums">
                  <thead>
                    <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                      <th className="pb-2 pr-3 font-medium">Leg</th>
                      <th className="pb-2 pr-3 font-medium">SPAN</th>
                      <th className="pb-2 pr-3 font-medium">Exposure</th>
                      <th className="pb-2 pr-3 font-medium">Premium Paid</th>
                      <th className="pb-2 font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {margin.legs.map((leg, i) => (
                      <tr key={i} className="border-b border-slate-50 last:border-0">
                        <td className="py-1.5 pr-3 font-medium text-slate-700">{leg.label}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{inr(leg.span)}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{inr(leg.exposure)}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{inr(leg.premium_paid)}</td>
                        <td className="py-1.5 tabular-nums font-semibold text-slate-800">{inr(leg.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
{margin.max_loss_theoretical !== null && (
                <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  Max theoretical loss (defined-risk): <strong>{inr(margin.max_loss_theoretical)}</strong>
                </p>
              )}
              <p className="mt-3 text-[11px] text-slate-400">
                {margin.disclaimer || "Estimate using rule-of-thumb SPAN + Exposure rates. Your broker's real margin file governs actual blocks."}
              </p>
            </Card>
          )}
        </>
      )}

      <Card
        title="Monte Carlo"
        subtitle={`GBM paths repriced through Black-Scholes at horizon${result ? "" : " A� run Analyze Payoff first to resolve legs"}`}
        actions={
              <div className="flex items-center gap-2">
                <select
                  value={paths}
                  onChange={(e) => setPaths(Number(e.target.value))}
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-xs text-slate-700"
                >
                  <option value={2000}>2,000</option>
                  <option value={5000}>5,000</option>
                  <option value={10000}>10,000</option>
                  <option value={20000}>20,000</option>
                </select>
                <button
                  onClick={runMonteCarlo}
                  disabled={mcBusy || legs.length === 0}
                  className="rounded-md bg-slate-800 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-900 disabled:opacity-50"
                >
                  {mcBusy ? "Simulating…" : "Run"}
                </button>
              </div>
            }
          >
            {!mc ? (
              <p className="py-6 text-center text-sm text-slate-400">
                Simulate P&L distribution across random market paths.
              </p>
            ) : (
              <div className="space-y-4">
                <Histogram bins={mc.bins} />
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-8">
                  <MetricCard label="Prob Profit" value={`${(mc.stats.prob_profit * 100).toFixed(1)}%`} tone={mc.stats.prob_profit >= 0.5 ? "positive" : "negative"} />
                  <MetricCard label="Mean P&L" value={inr(mc.stats.mean)} tone={mc.stats.mean >= 0 ? "positive" : "negative"} />
                  <MetricCard label="Median" value={inr(mc.stats.median)} />
                  <MetricCard label="Std Dev" value={inr(mc.stats.std)} />
                  <MetricCard label="P5" value={inr(mc.stats.p5)} tone="negative" />
                  <MetricCard label="P95" value={inr(mc.stats.p95)} tone="positive" />
                  <MetricCard label="VaR 95%" value={inr(mc.stats.var_95)} tone="negative" />
                  <MetricCard label="Vol Used" value={`${fmt(mc.vol_used_pct, 1)}%`} hint={`${mc.paths.toLocaleString("en-IN")} paths · ${mc.horizon_days}d horizon`} />
                </div>
              </div>
            )}
      </Card>
    </div>
  );
}
