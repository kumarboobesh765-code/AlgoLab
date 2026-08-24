"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type OptionChain } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

const UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"];

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export default function OptionChainPage() {
  const [underlying, setUnderlying] = useState("NIFTY");
  const [expiry, setExpiry] = useState<string | null>(null);
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [underlying, expiry]);

  const selectUnderlying = (u: string) => {
    setUnderlying(u);
    setLoading(true);
    setError(null);
    setExpiry(null);
  };

  const { atmStrike, maxCallOi, maxPutOi } = useMemo(() => {
    if (!chain || chain.strikes.length === 0) {
      return { atmStrike: null as number | null, maxCallOi: 0, maxPutOi: 0 };
    }
    return {
      atmStrike: chain.strikes.reduce((best, s) =>
        Math.abs(s.strike - chain.spot) < Math.abs(best - chain.spot) ? s.strike : best,
      chain.strikes[0].strike),
      maxCallOi: Math.max(...chain.strikes.map((s) => s.call_oi)),
      maxPutOi: Math.max(...chain.strikes.map((s) => s.put_oi)),
    };
  }, [chain]);

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
        {chain?.is_demo && <Badge tone="amber">DEMO DATA — synthetic</Badge>}
        {chain && (
          <select
            value={expiry ?? chain.expiry}
            onChange={(e) => {
              setExpiry(e.target.value);
              setLoading(true);
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

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}

      <Card
        title={`${underlying} Option Chain`}
        subtitle={
          chain
            ? `Spot ${fmt(chain.spot)} · Expiry ${chain.expiry} · Provider ${chain.provider}`
            : loading
              ? "Loading…"
              : undefined
        }
      >
        {!chain ? (
          <p className="py-10 text-center text-sm text-slate-400">
            {loading ? "Loading option chain…" : "No data"}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-[12px] tabular-nums">
              <thead>
                <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                  <th colSpan={8} className="pb-1 pr-2 text-center font-semibold text-blue-600">
                    Calls
                  </th>
                  <th className="pb-1 px-2 text-center font-semibold">Strike</th>
                  <th colSpan={8} className="pb-1 pl-2 text-center font-semibold text-red-600">
                    Puts
                  </th>
                </tr>
                <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                  <th className="py-1.5 pr-2 text-right font-medium">OI</th>
                  <th className="pr-2 text-right font-medium">Vol</th>
                  <th className="pr-2 text-right font-medium">IV %</th>
                  <th className="pr-2 text-right font-medium">Delta</th>
                  <th className="pr-2 text-right font-medium">Gamma</th>
                  <th className="pr-2 text-right font-medium">Theta</th>
                  <th className="pr-2 text-right font-medium">Vega</th>
                  <th className="pr-2 text-right font-medium">LTP</th>
                  <th className="px-2 text-center font-medium">—</th>
                  <th className="pl-2 text-right font-medium">LTP</th>
                  <th className="pl-2 text-right font-medium">Vega</th>
                  <th className="pl-2 text-right font-medium">Theta</th>
                  <th className="pl-2 text-right font-medium">Gamma</th>
                  <th className="pl-2 text-right font-medium">Delta</th>
                  <th className="pl-2 text-right font-medium">IV %</th>
                  <th className="pl-2 text-right font-medium">Vol</th>
                  <th className="pl-2 text-right font-medium">OI</th>
                </tr>
              </thead>
              <tbody>
                {chain.strikes.map((s) => {
                  const isAtm = s.strike === atmStrike;
                  return (
                    <tr
                      key={s.strike}
                      className={`border-b border-slate-50 last:border-0 ${
                        isAtm ? "bg-blue-50/70 font-medium" : ""
                      }`}
                    >
                      <td className={`py-1.5 pr-2 text-right ${s.call_oi === maxCallOi ? "text-blue-700" : "text-slate-600"}`}>
                        {fmt(s.call_oi / 1000, 0)}K{s.call_oi === maxCallOi ? " ●" : ""}
                      </td>
                      <td className="pr-2 text-right text-slate-500">{fmt(s.call_volume / 1000, 0)}K</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(s.call_iv, 1)}</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(s.call_delta, 2)}</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(s.call_gamma, 4)}</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(s.call_theta, 3)}</td>
                      <td className="pr-2 text-right text-slate-500">{fmt(s.call_vega, 3)}</td>
                      <td className="pr-2 text-right font-semibold text-slate-800">{fmt(s.call_ltp)}</td>
                      <td className={`px-2 text-center font-semibold ${isAtm ? "text-blue-700" : "text-slate-700"}`}>
                        {s.strike.toLocaleString("en-IN")}
                        {isAtm && <span className="ml-1 rounded bg-blue-600 px-1 py-px text-[9px] text-white">ATM</span>}
                      </td>
                      <td className="pl-2 text-right font-semibold text-slate-800">{fmt(s.put_ltp)}</td>
                      <td className="pl-2 text-right text-slate-500">{fmt(s.put_vega, 3)}</td>
                      <td className="pl-2 text-right text-slate-500">{fmt(s.put_theta, 3)}</td>
                      <td className="pl-2 text-right text-slate-500">{fmt(s.put_gamma, 4)}</td>
                      <td className="pl-2 text-right text-slate-500">{fmt(s.put_delta, 2)}</td>
                      <td className="pl-2 text-right text-slate-500">{fmt(s.put_iv, 1)}</td>
                      <td className="pl-2 text-right text-slate-500">{fmt(s.put_volume / 1000, 0)}K</td>
                      <td className={`pl-2 text-right ${s.put_oi === maxPutOi ? "text-blue-700" : "text-slate-600"}`}>
                        {fmt(s.put_oi / 1000, 0)}K{s.put_oi === maxPutOi ? " ●" : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-slate-400">
              ● highest OI · highlighted row = ATM. Greeks and IV are provider-reported.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
