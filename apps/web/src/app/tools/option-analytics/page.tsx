"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type OptionChain,
  type OptionChainAnalyticsResponse,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";

const UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"];

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function inr(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export default function OptionAnalyticsPage() {
  const [underlying, setUnderlying] = useState("NIFTY");
  const [expiry, setExpiry] = useState<string | null>(null);
  const [analytics, setAnalytics] = useState<OptionChainAnalyticsResponse | null>(null);
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const qs = expiry ? `?underlying=${underlying}&expiry=${expiry}` : `?underlying=${underlying}`;
    api<OptionChain>(`/market/option-chain${qs}`)
      .then((c) => {
        if (!cancelled) {
          setChain(c);
          setExpiry(c.expiry);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load option chain");
      });
    return () => { cancelled = true; };
  }, [underlying, expiry]);

  useEffect(() => {
    let cancelled = false;
    const qs = expiry ? `?underlying=${underlying}&expiry=${expiry}` : `?underlying=${underlying}`;
    api<OptionChainAnalyticsResponse>(`/options/analytics${qs}`)
      .then((a) => {
        if (!cancelled) {
          setAnalytics(a);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load analytics");
        }
      });
    return () => { cancelled = true; };
  }, [underlying, expiry]);

  const selectUnderlying = (u: string) => {
    setUnderlying(u);
    setError(null);
    setExpiry(null);
    setAnalytics(null);
    setChain(null);
  };

  const atmStrike = useMemo(() => {
    if (!chain || chain.strikes.length === 0) return null;
    return chain.strikes.reduce((best, s) =>
      Math.abs(s.strike - chain.spot) < Math.abs(best - chain.spot) ? s.strike : best,
    chain.strikes[0].strike);
  }, [chain]);

  const maxPainStrike = analytics?.max_pain?.max_pain_strike;
  const maxPainValue = analytics?.max_pain?.min_pain;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {UNDERLYINGS.map((u) => (
            <button
              key={u}
              onClick={() => selectUnderlying(u)}
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
        <div className="flex items-center gap-3">
          {chain?.is_demo && <Badge tone="amber">DEMO DATA — synthetic</Badge>}
          {chain && (
            <select
              value={expiry ?? chain.expiry}
              onChange={(e) => {
                setExpiry(e.target.value);
                setError(null);
              }}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-xs text-slate-700"
            >
              {chain.expiries.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}

      {/* Overview Cards */}
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <Card title="Spot" subtitle={chain ? `Expiry ${chain.expiry}` : "Loading…"}>
          <div className="text-3xl font-bold tabular-nums text-slate-800">
            {chain ? fmt(chain.spot) : "—"}
          </div>
        </Card>
        <Card title="PCR (OI)">
          <div className="text-3xl font-bold tabular-nums text-slate-800">
            {analytics?.pcr?.pcr_oi ? fmt(analytics.pcr.pcr_oi, 3) : "—"}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            Vol PCR: {analytics?.pcr?.pcr_volume ? fmt(analytics.pcr.pcr_volume, 3) : "—"}
          </div>
        </Card>
        <Card title="Max Pain">
          <div className="text-3xl font-bold tabular-nums text-slate-800">
            {maxPainStrike !== undefined ? maxPainStrike.toLocaleString("en-IN") : "—"}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            Min Pain: {maxPainValue !== undefined ? inr(maxPainValue) : "—"}
          </div>
        </Card>
        <Card title="ATM IV">
          <div className="text-3xl font-bold tabular-nums text-slate-800">
            {analytics?.iv_surface?.atm_iv ? fmt(analytics.iv_surface.atm_iv * 100, 2) + "%" : "—"}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            Skew: {analytics?.iv_surface?.skew ? fmt(analytics.iv_surface.skew * 100, 2) + "%" : "—"}
          </div>
        </Card>
      </div>

      {/* PCR Details */}
      {analytics?.pcr && (
        <Card title="Put-Call Ratio Details" subtitle="OI and Volume based PCR across strikes">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4 mb-4">
            <MetricCard label="Total Call OI" value={fmt((analytics.pcr.total_call_oi ?? 0) / 100000, 1) + "L"} />
            <MetricCard label="Total Put OI" value={fmt((analytics.pcr.total_put_oi ?? 0) / 100000, 1) + "L"} />
            <MetricCard label="Total Call Vol" value={fmt((analytics.pcr.total_call_volume ?? 0) / 1000, 0) + "K"} />
            <MetricCard label="Total Put Vol" value={fmt((analytics.pcr.total_put_volume ?? 0) / 1000, 0) + "K"} />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px] text-left text-[11px] tabular-nums">
              <thead>
                <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                  <th className="py-1.5 pr-3 text-right font-medium">Strike</th>
                  <th className="pr-3 text-right font-medium">Call OI</th>
                  <th className="pr-3 text-right font-medium">Put OI</th>
                  <th className="pr-3 text-right font-medium">PCR (OI)</th>
                  <th className="pr-3 text-right font-medium">Call Vol</th>
                  <th className="pr-3 text-right font-medium">Put Vol</th>
                  <th className="pr-3 text-right font-medium">PCR (Vol)</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(analytics.pcr.strike_pcr)
                  .map(([strike, pcr]) => ({
                    strike: Number(strike),
                    pcr,
                    callOi: chain?.strikes.find((s) => s.strike === Number(strike))?.call_oi ?? 0,
                    putOi: chain?.strikes.find((s) => s.strike === Number(strike))?.put_oi ?? 0,
                    callVol: chain?.strikes.find((s) => s.strike === Number(strike))?.call_volume ?? 0,
                    putVol: chain?.strikes.find((s) => s.strike === Number(strike))?.put_volume ?? 0,
                  }))
                  .sort((a, b) => a.strike - b.strike)
                  .slice(0, 30)
                  .map((row) => (
                    <tr
                      key={row.strike}
                      className={`border-b border-slate-50 last:border-0 ${
                        atmStrike === row.strike ? "bg-blue-50/70 font-medium" : ""
                      }`}
                    >
                      <td className={`py-1.5 pr-3 text-right ${atmStrike === row.strike ? "text-blue-700" : "text-slate-700"}`}>
                        {row.strike.toLocaleString("en-IN")}
                        {atmStrike === row.strike && <span className="ml-1 rounded bg-blue-600 px-1 py-px text-[9px] text-white">ATM</span>}
                      </td>
                      <td className="pr-3 text-right text-slate-600">{fmt(row.callOi / 1000, 0)}K</td>
                      <td className="pr-3 text-right text-slate-600">{fmt(row.putOi / 1000, 0)}K</td>
                      <td className="pr-3 text-right font-medium text-slate-800">{fmt(row.pcr, 3)}</td>
                      <td className="pr-3 text-right text-slate-500">{fmt(row.callVol / 1000, 0)}K</td>
                      <td className="pr-3 text-right text-slate-500">{fmt(row.putVol / 1000, 0)}K</td>
                      <td className="pr-3 text-right text-slate-500">
                        {row.callVol > 0 ? fmt(row.putVol / row.callVol, 3) : "—"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Max Pain Details */}
      {analytics?.max_pain && (
        <Card title="Max Pain Analysis" subtitle="Strike where option buyers lose maximum (expiry assumption)">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4 mb-4">
            <MetricCard label="Max Pain Strike" value={maxPainStrike !== undefined ? maxPainStrike.toLocaleString("en-IN") : "—"} />
            <MetricCard label="Min Pain Value" value={inr(maxPainValue)} />
            <MetricCard label="Current Spot" value={chain ? fmt(chain.spot) : "—"} />
            <MetricCard
              label="Distance from Spot"
              value={maxPainStrike !== undefined && chain ? fmt(((maxPainStrike - chain.spot) / chain.spot) * 100, 2) + "%" : "—"}
              tone={maxPainStrike !== undefined && chain && maxPainStrike > chain.spot ? "positive" : "negative"}
            />
          </div>
          {chain && analytics.max_pain.pain_by_strike && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] text-left text-[11px] tabular-nums">
                <thead>
                  <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                    <th className="py-1.5 pr-3 text-right font-medium">Strike</th>
                    <th className="pr-3 text-right font-medium">Total Pain</th>
                    <th className="pr-3 text-right font-medium">Call Pain</th>
                    <th className="text-right font-medium">Put Pain</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(analytics.max_pain.pain_by_strike ?? {})
                    .map(([strike, pain]: [string, number]) => ({
                      strike: Number(strike),
                      pain,
                      callOi: chain.strikes.find((s) => s.strike === Number(strike))?.call_oi ?? 0,
                      putOi: chain.strikes.find((s) => s.strike === Number(strike))?.put_oi ?? 0,
                    }))
                    .sort((a, b) => a.strike - b.strike)
                    .slice(0, 25)
                    .map((row) => {
                      const spot = chain?.spot ?? 0;
                      const callPain = row.strike < spot ? (spot - row.strike) * row.callOi : 0;
                      const putPain = row.strike > spot ? (row.strike - spot) * row.putOi : 0;
                      return (
                        <tr
                          key={row.strike}
                          className={`border-b border-slate-50 last:border-0 ${
                            atmStrike === row.strike ? "bg-blue-50/70 font-medium" :
                            maxPainStrike === row.strike ? "bg-amber-50/70 font-bold" : ""
                          }`}
                        >
                          <td className={`py-1.5 pr-3 text-right ${atmStrike === row.strike ? "text-blue-700" : "text-slate-700"}`}>
                            {row.strike.toLocaleString("en-IN")}
                            {atmStrike === row.strike && <span className="ml-1 rounded bg-blue-600 px-1 py-px text-[9px] text-white">ATM</span>}
                            {maxPainStrike === row.strike && <span className="ml-1 rounded bg-amber-600 px-1 py-px text-[9px] text-white">MAX PAIN</span>}
                          </td>
                          <td className="pr-3 text-right text-slate-800">{inr(row.pain)}</td>
                          <td className="pr-3 text-right text-slate-500">{inr(callPain)}</td>
                          <td className="text-right text-slate-500">{inr(putPain)}</td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* IV Surface */}
      {analytics?.iv_surface && (
        <Card title="Implied Volatility Surface" subtitle="ATM IV and skew across strikes">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4 mb-4">
            <MetricCard label="ATM IV" value={fmt((analytics.iv_surface.atm_iv ?? 0) * 100, 2) + "%"} />
            <MetricCard label="Skew" value={fmt((analytics.iv_surface.skew ?? 0) * 100, 2) + "%"} hint="25-delta put IV - 25-delta call IV" />
            <MetricCard label="Kurtosis" value={fmt((analytics.iv_surface.kurtosis ?? 0) * 100, 2) + "%"} />
            <MetricCard label="IV Points" value={String(analytics.iv_surface.points?.length ?? 0)} />
          </div>
          {analytics.iv_surface.points && analytics.iv_surface.points.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] text-left text-[11px] tabular-nums">
                <thead>
                  <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                    <th className="py-1.5 pr-3 text-right font-medium">Strike</th>
                    <th className="pr-3 text-right font-medium">Expiry</th>
                    <th className="pr-3 text-right font-medium">DTE</th>
                    <th className="pr-3 text-right font-medium">IV %</th>
                    <th className="pr-3 text-right font-medium">Delta</th>
                    <th className="text-right font-medium">Moneyness</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.iv_surface.points
                    .slice(0, 40)
                    .map((p: { strike: number; expiry: string; days_to_expiry: number; iv: number; delta: number; moneyness: number }) => (
                      <tr
                        key={`${p.strike}-${p.expiry}`}
                        className="border-b border-slate-50 last:border-0"
                      >
                        <td className="py-1.5 pr-3 text-right text-slate-700">{fmt(p.strike)}</td>
                        <td className="pr-3 text-right text-slate-500">{p.expiry}</td>
                        <td className="pr-3 text-right text-slate-500">{p.days_to_expiry}</td>
                        <td className="pr-3 text-right text-slate-800">{fmt(p.iv * 100, 2)}%</td>
                        <td className="pr-3 text-right text-slate-500">{fmt(p.delta, 3)}</td>
                        <td className="text-right text-slate-500">{fmt(p.moneyness, 4)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* IV Rank/Percentile */}
      {analytics?.iv_rank_percentile && (
        <Card title="IV Rank & Percentile" subtitle="Current IV vs historical range (52-week)">
          <div className="grid gap-3 md:grid-cols-4">
            <MetricCard label="Current IV" value={fmt((analytics.iv_rank_percentile.current_iv ?? 0) * 100, 2) + "%"} />
            <MetricCard label="IV Rank" value={fmt(analytics.iv_rank_percentile.iv_rank ?? 0, 1) + "%"} hint="Position in 52-week range" />
            <MetricCard label="IV Percentile" value={fmt(analytics.iv_rank_percentile.iv_percentile ?? 0, 1) + "%"} hint="% of days IV was lower" />
            <MetricCard label="52W Range" value={`${fmt((analytics.iv_rank_percentile.iv_52w_low ?? 0) * 100, 2)}% - ${fmt((analytics.iv_rank_percentile.iv_52w_high ?? 0) * 100, 2)}%`} />
          </div>
        </Card>
      )}

      {/* Greeks Heatmap */}
      {analytics?.greeks_heatmap && (
        <Card title="Greeks Heatmap (Net by Strike)" subtitle="Aggregated Greeks weighted by open interest">
          <div className="grid gap-3 md:grid-cols-4 mb-4">
            <MetricCard label="Net Delta" value={fmt(analytics.greeks_heatmap.net_delta ?? 0, 1)} tone={((analytics.greeks_heatmap.net_delta ?? 0) >= 0 ? "positive" : "negative")} />
            <MetricCard label="Net Gamma" value={fmt(analytics.greeks_heatmap.net_gamma ?? 0, 3)} />
            <MetricCard label="Net Theta" value={inr(analytics.greeks_heatmap.net_theta)} tone={((analytics.greeks_heatmap.net_theta ?? 0) >= 0 ? "positive" : "negative")} hint="per day" />
            <MetricCard label="Net Vega" value={fmt(analytics.greeks_heatmap.net_vega ?? 0, 1)} />
          </div>
          {analytics.greeks_heatmap.strike_greeks && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[700px] text-left text-[11px] tabular-nums">
                <thead>
                  <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                    <th className="py-1.5 pr-3 text-right font-medium">Strike</th>
                    <th className="pr-3 text-right font-medium">Call OI</th>
                    <th className="pr-3 text-right font-medium">Put OI</th>
                    <th className="pr-3 text-right font-medium">Net Δ</th>
                    <th className="pr-3 text-right font-medium">Net Γ</th>
                    <th className="pr-3 text-right font-medium">Net Θ</th>
                    <th className="pr-3 text-right font-medium">Net Vega</th>
                    <th className="pr-3 text-right font-medium">Call Δ</th>
                    <th className="text-right font-medium">Put Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(analytics.greeks_heatmap.strike_greeks)
                    .map(([strike, g]) => ({
                      strike: Number(strike),
                      call_oi: g.call_oi,
                      put_oi: g.put_oi,
                      delta: g.delta,
                      gamma: g.gamma,
                      theta: g.theta,
                      vega: g.vega,
                      call_delta: g.call_delta,
                      put_delta: g.put_delta,
                    }))
                    .sort((a, b) => a.strike - b.strike)
                    .map((row) => (
                      <tr
                        key={row.strike}
                        className={`border-b border-slate-50 last:border-0 ${
                          atmStrike === row.strike ? "bg-blue-50/70 font-medium" : ""
                        }`}
                      >
                        <td className={`py-1.5 pr-3 text-right ${atmStrike === row.strike ? "text-blue-700" : "text-slate-700"}`}>
                          {row.strike.toLocaleString("en-IN")}
                          {atmStrike === row.strike && <span className="ml-1 rounded bg-blue-600 px-1 py-px text-[9px] text-white">ATM</span>}
                        </td>
                        <td className="pr-3 text-right text-slate-600">{fmt((row.call_oi ?? 0) / 1000, 0)}K</td>
                        <td className="pr-3 text-right text-slate-600">{fmt((row.put_oi ?? 0) / 1000, 0)}K</td>
                        <td className="pr-3 text-right font-medium text-slate-800">{fmt(row.delta ?? 0, 2)}</td>
                        <td className="pr-3 text-right text-slate-500">{fmt(row.gamma ?? 0, 5)}</td>
                        <td className="pr-3 text-right text-slate-500">{fmt(row.theta ?? 0, 1)}</td>
                        <td className="pr-3 text-right text-slate-500">{fmt(row.vega ?? 0, 1)}</td>
                        <td className="pr-3 text-right text-blue-600">{fmt(row.call_delta ?? 0, 3)}</td>
                        <td className="text-right text-red-600">{fmt(row.put_delta ?? 0, 3)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Support / Resistance from OI */}
      {analytics?.max_pain?.support_resistance && (
        <Card title="Support & Resistance (OI Concentration)" subtitle="High Call OI = Resistance, High Put OI = Support">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <h4 className="text-sm font-semibold text-red-700 mb-2">Resistance (Call OI)</h4>
              <ul className="space-y-1">
                {analytics.max_pain.support_resistance.resistance?.slice(0, 5).map((r: { strike: number; oi: number }, i: number) => (
                  <li key={i} className="flex justify-between text-sm">
                    <span className="text-slate-700">{fmt(r.strike)}</span>
                    <span className="text-slate-500">{fmt(r.oi / 1000, 0)}K OI</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-emerald-700 mb-2">Support (Put OI)</h4>
              <ul className="space-y-1">
                {analytics.max_pain.support_resistance.support?.slice(0, 5).map((s: { strike: number; oi: number }, i: number) => (
                  <li key={i} className="flex justify-between text-sm">
                    <span className="text-slate-700">{fmt(s.strike)}</span>
                    <span className="text-slate-500">{fmt(s.oi / 1000, 0)}K OI</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}