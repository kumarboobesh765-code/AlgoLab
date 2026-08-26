"use client";

import { useEffect, useState } from "react";
import { api, apiBlob } from "@/lib/api";
import { Card } from "@/components/ui/Card";

interface TaxTrade {
  exit_date: string;
  underlying: string;
  direction: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  realized_pnl: number;
  holding_days: number;
  category: string;
}

interface TaxReport {
  fy: string;
  start: string;
  end: string;
  segment: string;
  total_trades: number;
  winners: number;
  losers: number;
  stcg_pnl: number;
  ltcg_pnl: number;
  gross_profit: number;
  gross_loss: number;
  net_pnl: number;
  fno_turnover_abs_pnl: number;
  est_tax_stcg: number;
  est_tax_ltcg: number;
  trades: TaxTrade[];
}

function fyOptions(): string[] {
  const now = new Date();
  const currentStart = now >= new Date(now.getFullYear(), 3, 1) ? now.getFullYear() : now.getFullYear() - 1;
  return [0, 1, 2].map((i) => {
    const y = currentStart - i;
    return `${y}-${String(y + 1).slice(2)}`;
  });
}

const inr = (v: number): string =>
  v.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

export default function TaxReportPage() {
  const [fy, setFy] = useState(fyOptions()[0]);
  const [segment, setSegment] = useState<"equity" | "fno">("equity");
  const [report, setReport] = useState<TaxReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<TaxReport>(`/tax/report?fy=${fy}&segment=${segment}`)
      .then((r) => {
        if (!cancelled) {
          setReport(r);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load report");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fy, segment]);

  const stale = !report || report.fy !== fy || report.segment !== segment;
  const showLoading = loading && (report === null || stale);

  async function downloadCsv() {
    try {
      const blob = await apiBlob(`/tax/report/csv?fy=${fy}&segment=${segment}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tax_${segment}_${fy}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("CSV download failed");
    }
  }

  return (
    <div className="space-y-4">
      <Card
        title="Tax Report"
        subtitle={`Closed paper trades for FY ${fy} (${segment === "fno" ? "business income view" : "capital gains view"})`}
        actions={
          <div className="flex items-center gap-2">
            <select value={fy} onChange={(e) => setFy(e.target.value)} className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs">
              {fyOptions().map((f) => <option key={f} value={f}>FY {f}</option>)}
            </select>
            <div className="flex overflow-hidden rounded-lg border border-slate-200">
              {(["equity", "fno"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSegment(s)}
                  className={`px-3 py-1.5 text-xs font-medium ${segment === s ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
                >
                  {s === "fno" ? "F&O" : "Equity"}
                </button>
              ))}
            </div>
            <button onClick={downloadCsv} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-blue-300 hover:text-blue-700">
              CSV
            </button>
          </div>
        }
      >
        {error && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">{error}</p>
        )}
        {showLoading && <p className="py-8 text-center text-sm text-slate-400">Loading…</p>}
        {!loading && report && (
          <>
            <div className="grid gap-2 sm:grid-cols-4">
              <SummaryCell label="Total trades" value={String(report.total_trades)} />
              <SummaryCell label="Winners / Losers" value={`${report.winners} / ${report.losers}`} />
              <SummaryCell label="Net P&L" value={`₹${inr(report.net_pnl)}`} tone={report.net_pnl >= 0 ? "green" : "red"} />
              {segment === "equity" ? (
                <>
                  <SummaryCell label="STCG P&L" value={`₹${inr(report.stcg_pnl)}`} tone={report.stcg_pnl >= 0 ? "green" : "red"} />
                  <SummaryCell label="LTCG P&L" value={`₹${inr(report.ltcg_pnl)}`} tone={report.ltcg_pnl >= 0 ? "green" : "red"} />
                  <SummaryCell label="Est. tax (STCG @20%)" value={`₹${inr(report.est_tax_stcg)}`} />
                  <SummaryCell label="Est. tax (LTCG @12.5%)" value={`₹${inr(report.est_tax_ltcg)}`} note="after ₹1.25L exempt" />
                </>
              ) : (
                <>
                  <SummaryCell label="Turnover (Σ|P&L|)" value={`₹${inr(report.fno_turnover_abs_pnl)}`} />
                  <SummaryCell label="Gross profit" value={`₹${inr(report.gross_profit)}`} tone="green" />
                  <SummaryCell label="Gross loss" value={`₹${inr(report.gross_loss)}`} tone="red" />
                </>
              )}
            </div>
            <p className="mt-2 text-[11px] text-slate-400">
              Estimates use slab-less flat rates for simplicity — consult a CA before filing. F&O income is taxed as business income at slab rates.
            </p>

            {report.trades.length > 0 && (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-[12px]">
                  <thead>
                    <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                      <th className="pb-2 pr-3 font-medium">Exit date</th>
                      <th className="pb-2 pr-3 font-medium">Underlying</th>
                      <th className="pb-2 pr-3 font-medium">Dir</th>
                      <th className="pb-2 pr-3 font-medium">Qty</th>
                      <th className="pb-2 pr-3 font-medium">Entry</th>
                      <th className="pb-2 pr-3 font-medium">Exit</th>
                      <th className="pb-2 pr-3 font-medium">P&L</th>
                      <th className="pb-2 pr-3 font-medium">Days</th>
                      <th className="pb-2 font-medium">Category</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.trades.map((t, i) => (
                      <tr key={`${t.exit_date}-${i}`} className="border-b border-slate-50 last:border-0">
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{t.exit_date}</td>
                        <td className="py-1.5 pr-3 font-medium text-slate-700">{t.underlying}</td>
                        <td className="py-1.5 pr-3 capitalize text-slate-500">{t.direction}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{t.quantity}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{inr(t.entry_price)}</td>
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{inr(t.exit_price)}</td>
                        <td className={`py-1.5 pr-3 tabular-nums font-semibold ${t.realized_pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                          {inr(t.realized_pnl)}
                        </td>
                        <td className="py-1.5 pr-3 tabular-nums text-slate-500">{t.holding_days}</td>
                        <td className="py-1.5">
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            t.category === "STCG" ? "bg-blue-50 text-blue-700"
                            : t.category === "LTCG" ? "bg-violet-50 text-violet-700"
                            : "bg-amber-50 text-amber-700"
                          }`}>
                            {t.category}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}

function SummaryCell({ label, value, tone, note }: { label: string; value: string; tone?: "green" | "red"; note?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold tabular-nums ${
        tone === "green" ? "text-emerald-600" : tone === "red" ? "text-red-600" : "text-slate-800"
      }`}>
        {value}
      </p>
      {note && <p className="text-[10px] text-slate-400">{note}</p>}
    </div>
  );
}
