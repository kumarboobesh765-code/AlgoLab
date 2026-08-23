"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PaperAccount, PaperAccountDetail, PaperPosition, Strategy } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";
import { downloadCsv } from "@/lib/csv";

function fmtMoney(n: number): string {
  return `${n < 0 ? "-" : ""}₹${Math.abs(Math.round(n)).toLocaleString("en-IN")}`;
}

function pctOf(part: number, whole: number): string {
  if (whole <= 0) return "0.00";
  return ((part / whole) * 100).toFixed(2);
}

interface PositionRow extends PaperPosition {
  accountName: string;
  strategyName: string;
}

export default function PortfolioPage() {
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [details, setDetails] = useState<Record<string, PaperAccountDetail>>({});
  const [strategies, setStrategies] = useState<Strategy[]>([]);

  const load = useCallback(() => {
    if (!auth.user) return;
    setLoading(true);
    setError(null);
    let loaded: PaperAccount[] = [];
    api<PaperAccount[]>("/paper/accounts")
      .then((accs) => {
        loaded = accs;
        setAccounts(accs);
        return api<Strategy[]>("/strategies");
      })
      .then((strats) => {
        setStrategies(strats);
        return Promise.all(
          loaded.map((a) => api<PaperAccountDetail>(`/paper/accounts/${a.id}`)),
        );
      })
      .then((ds) => {
        const map: Record<string, PaperAccountDetail> = {};
        loaded.forEach((a, i) => {
          map[a.id] = ds[i];
        });
        setDetails(map);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [auth.user]);

  useEffect(() => {
    // Defer via microtask so the effect body itself never calls setState
    Promise.resolve().then(load);
  }, [load]);

  const data = useMemo(() => {
    const strategyNames = new Map(strategies.map((s) => [s.id, s.name]));
    const rows: PositionRow[] = [];
    let initial = 0;
    let equity = 0;
    let unrealized = 0;
    for (const acc of accounts) {
      initial += acc.initial_capital;
      const d = details[acc.id];
      if (!d) continue;
      equity += d.equity;
      unrealized += d.unrealized_pnl;
      for (const p of d.open_positions) {
        rows.push({
          ...p,
          accountName: acc.name,
          strategyName:
            (p.strategy_id && strategyNames.get(p.strategy_id)) || p.strategy_id?.slice(0, 8) || "—",
        });
      }
    }
    return { rows, initial, equity, unrealized };
  }, [accounts, details, strategies]);

  if (!auth.user) {
    return <p className="text-sm text-slate-500">Connecting to the API…</p>;
  }
  if (loading) return <p className="text-sm text-slate-500">Loading portfolio…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Portfolio</h2>
          <p className="text-sm text-slate-500">
            Consolidated paper-trading capital and open positions across all accounts.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard label="Paper accounts" value={String(accounts.length)} />
        <MetricCard label="Allocated capital" value={fmtMoney(data.initial)} />
        <MetricCard
          label="Current equity"
          value={fmtMoney(data.equity)}
          tone={data.equity >= data.initial ? "positive" : "negative"}
          hint={`${data.equity >= data.initial ? "+" : ""}${pctOf(data.equity - data.initial, data.initial)}% overall`}
        />
        <MetricCard
          label="Unrealized P&L"
          value={fmtMoney(data.unrealized)}
          tone={data.unrealized >= 0 ? "positive" : "negative"}
        />
      </div>

      <Card
        title="Open positions"
        subtitle={`${data.rows.length} position(s) across ${accounts.length} account(s)`}
        actions={
          data.rows.length > 0 ? (
            <button
              onClick={() =>
                downloadCsv(
                  "open_positions.csv",
                  ["account", "strategy", "direction", "qty", "entry", "last", "unrealized_pnl"],
                  data.rows.map((p) => [
                    p.accountName, p.strategyName, p.direction, p.quantity,
                    p.entry_price, p.last_close ?? "", p.unrealized_pnl ?? "",
                  ]),
                )
              }
              className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50"
            >
              Export CSV
            </button>
          ) : undefined
        }
      >
        {data.rows.length === 0 ? (
          <p className="py-10 text-center text-sm text-slate-400">
            No open positions. Start a forward test or place paper trades.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-2 py-2">Account</th>
                  <th className="px-2 py-2">Strategy</th>
                  <th className="px-2 py-2">Side</th>
                  <th className="px-2 py-2 text-right">Qty</th>
                  <th className="px-2 py-2 text-right">Entry</th>
                  <th className="px-2 py-2 text-right">Last</th>
                  <th className="px-2 py-2 text-right">Unrealized</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.rows.map((p) => (
                  <tr key={p.id}>
                    <td className="px-2 py-2">{p.accountName}</td>
                    <td className="px-2 py-2 font-medium text-slate-900">{p.strategyName}</td>
                    <td className="px-2 py-2">
                      <Badge tone={p.direction === "long" ? "green" : "red"}>{p.direction}</Badge>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">{p.quantity}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{p.entry_price.toFixed(2)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">
                      {p.last_close != null ? p.last_close.toFixed(2) : "—"}
                    </td>
                    <td
                      className={`px-2 py-2 text-right tabular-nums ${
                        (p.unrealized_pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
                      }`}
                    >
                      {p.unrealized_pnl != null ? fmtMoney(p.unrealized_pnl) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Accounts" actions={<Link href="/tools/paper-accounts" className="text-xs font-medium text-indigo-600 hover:underline">Manage →</Link>}>
        {accounts.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">No paper accounts yet.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {accounts.map((a) => {
              const d = details[a.id];
              const pnl = d ? d.equity - a.initial_capital : 0;
              return (
                <div key={a.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-900">{a.name}</span>
                    <Badge tone={a.status === "active" ? "green" : "slate"}>{a.status}</Badge>
                  </div>
                  <dl className="mt-3 space-y-1 text-xs text-slate-600">
                    <div className="flex justify-between">
                      <dt>Initial capital</dt>
                      <dd className="tabular-nums">{fmtMoney(a.initial_capital)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Cash balance</dt>
                      <dd className="tabular-nums">{fmtMoney(a.cash_balance)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Equity</dt>
                      <dd className={`tabular-nums font-medium ${pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                        {d ? `${fmtMoney(d.equity)} (${pnl >= 0 ? "+" : ""}${pctOf(pnl, a.initial_capital)}%)` : "…"}
                      </dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Open / closed positions</dt>
                      <dd>{d ? `${d.open_positions.length} / ${d.closed_positions.length}` : "…"}</dd>
                    </div>
                  </dl>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <p className="text-xs text-slate-400">
        Paper trading only — no real money. Equity marks open positions at the latest available close.
      </p>
    </div>
  );
}
