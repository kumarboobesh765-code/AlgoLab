"use client";

import { useCallback, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { api, type OosValidationResponse } from "@/lib/api";

function fmtMoney(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function fmtPct(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function shortDate(iso: string): string {
  return iso.slice(0, 10);
}

function Cell({ label, is, oos }: { label: string; is: unknown; oos: unknown }) {
  const a = Number(is);
  const b = Number(oos);
  const worse = Number.isFinite(a) && Number.isFinite(b) ? b < a : false;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">{fmtPct(is)}</span>
        <span
          className={`text-sm font-semibold ${worse ? "text-red-600" : "text-emerald-600"}`}
        >
          {fmtPct(oos)}
        </span>
      </div>
    </div>
  );
}

/**
 * In/Out-of-Sample panel.
 *
 * Renders the split only after an explicit click: it runs a second backtest, so
 * it must not fire on every report view. The verdict is deliberately shown as a
 * number plus a plain reading rather than a green/red badge, because a single
 * efficiency threshold on a 30-trade sample is not enough to call a strategy
 * robust or broken.
 *
 * Mount this with `key={strategy.id}`: the split belongs to one strategy, and a
 * remount is how the panel drops the previous strategy's result. Resetting via
 * an effect would be a second render pass to achieve the same thing.
 */
export function OutOfSamplePanel({ strategyId }: { strategyId: string }) {
  const [data, setData] = useState<OosValidationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const run = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api<OosValidationResponse>("/backtests/validate", {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId }),
      });
      setData(res);
      setOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Validation failed");
    } finally {
      setBusy(false);
    }
  }, [strategyId]);

  if (!open && !data) {
    return (
      <div className="mt-4">
        <button
          onClick={run}
          disabled={busy}
          className="rounded border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 hover:bg-sky-100 disabled:opacity-50"
        >
          {busy ? "Splitting…" : "Validate: In-Sample vs Out-of-Sample"}
        </button>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </div>
    );
  }

  if (!data) return null;

  const { in_sample: isWin, out_of_sample: oosWin } = data.windows;
  const deg = data.degradation;
  const efficiency = deg.efficiency_ratio;
  const weakSample = Number(deg.oos_trades) < 10;
  let reading: string;
  let tone: "green" | "red" | "amber";
  if (weakSample) {
    reading = `Only ${deg.oos_trades} out-of-sample trades — too few to judge. Widen the date range.`;
    tone = "amber";
  } else if (!deg.oos_is_profitable) {
    reading =
      "The edge did not survive on unseen data. This is the signature of a strategy fitted to its own history.";
    tone = "red";
  } else if (efficiency !== null && efficiency < 0.5) {
    reading = `Profitable out of sample, but only ${(efficiency * 100).toFixed(0)}% of the in-sample return carried over. Treat with caution.`;
    tone = "amber";
  } else {
    reading = "The edge held up on data the strategy was not built from.";
    tone = "green";
  }

  return (
    <div className="mt-4 space-y-3">
      <Card
        title="In-Sample vs Out-of-Sample"
        subtitle={`Split at ${shortDate(data.split_time)} · ${data.bars_used} bars · ${data.warmup_bars} bars of indicator warm-up carried into the OOS leg`}
        actions={
          <button
            onClick={() => setOpen(false)}
            className="text-[11px] font-medium text-slate-500 hover:text-slate-700"
          >
            Hide
          </button>
        }
      >
        <div className="mb-3 flex items-center justify-between text-[11px] font-medium text-slate-500">
          <span>
            IN-SAMPLE {shortDate(isWin.start)} → {shortDate(isWin.end)}
          </span>
          <span className="flex items-center gap-2">
            OUT-OF-SAMPLE {shortDate(oosWin.start)} → {shortDate(oosWin.end)}
            <Badge tone={tone}>{weakSample ? "too few trades" : deg.oos_is_profitable ? "profitable" : "unprofitable"}</Badge>
          </span>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Cell label="Return" is={deg.is_return_pct} oos={deg.oos_return_pct} />
          <Cell label="Sharpe" is={deg.is_sharpe} oos={deg.oos_sharpe} />
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
            <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
              Efficiency ratio
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-900">
              {efficiency === null ? "n/a" : efficiency.toFixed(2)}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
            <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
              OOS trades
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{deg.oos_trades}</div>
          </div>
        </div>

        <p
          className={`mt-3 rounded-md px-3 py-2 text-xs ring-1 ring-inset ${
            tone === "green"
              ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
              : tone === "amber"
                ? "bg-amber-50 text-amber-700 ring-amber-200"
                : "bg-red-50 text-red-700 ring-red-200"
          }`}
        >
          {reading}
        </p>

        <p className="mt-2 text-[11px] text-slate-500">
          Net P&amp;L — in-sample {fmtMoney(isWin.summary.net_pnl)} · out-of-sample{" "}
          {fmtMoney(oosWin.summary.net_pnl)}. Efficiency below ~0.5 conventionally indicates
          curve fitting; it is shown as a number rather than a verdict because a single
          threshold on a small sample is not decisive.
        </p>
      </Card>
    </div>
  );
}