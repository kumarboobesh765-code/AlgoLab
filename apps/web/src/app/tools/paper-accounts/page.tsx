"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type PaperAccount,
  type PaperAccountCreate,
  type PaperAccountDetail,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

function fmtMoney(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export default function PaperAccountsPage() {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [selected, setSelected] = useState<PaperAccountDetail | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [capital, setCapital] = useState("100000");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api<PaperAccount[]>("/paper/accounts")
      .then(setAccounts)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function createAccount() {
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api<PaperAccount>("/paper/accounts", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          initial_capital: Number(capital) || 100000,
        } as PaperAccountCreate),
      });
      setName("");
      setCapital("100000");
      setShowCreate(false);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create account");
    } finally {
      setCreating(false);
    }
  }

  async function deleteAccount(a: PaperAccount) {
    if (!window.confirm(`Delete paper account “${a.name}” and all its orders/positions?`)) return;
    setError(null);
    try {
      await api(`/paper/accounts/${a.id}`, { method: "DELETE" });
      if (selected?.id === a.id) setSelected(null);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete account");
    }
  }

  async function loadDetail(id: string) {
    setError(null);
    try {
      const detail = await api<PaperAccountDetail>(`/paper/accounts/${id}`);
      setSelected(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load account details");
    }
  }

  return (
    <div className="space-y-4">
      <Card
        title="Paper Accounts"
        subtitle="Virtual money accounts for forward testing — never connected to real brokers."
        actions={
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700"
          >
            {showCreate ? "Cancel" : "+ New Account"}
          </button>
        }
      >
        {showCreate && (
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <label className="block text-xs font-medium text-slate-500">
              Name
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Paper Account"
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              />
            </label>
            <label className="block text-xs font-medium text-slate-500">
              Initial Capital
              <input
                type="number"
                value={capital}
                min="1"
                onChange={(e) => setCapital(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              />
            </label>
            <div className="flex items-end">
              <button
                onClick={createAccount}
                disabled={creating || !name.trim()}
                className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {creating ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        )}
        {error && <p className="text-xs text-red-600">{error}</p>}

        {accounts.length === 0 ? (
          <p className="text-xs text-slate-500">
            No paper accounts yet. Create one to start forward testing.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {accounts.map((a) => (
              <li key={a.id} className="flex items-center gap-2">
                <button
                  onClick={() => loadDetail(a.id)}
                  className="flex flex-1 items-center justify-between gap-3 py-2 text-left text-xs hover:bg-slate-50"
                >
                  <span className="flex items-center gap-2">
                    <Badge tone={a.status === "active" ? "green" : "red"}>{a.status}</Badge>
                    <span className="font-medium text-slate-700">{a.name}</span>
                  </span>
                  <span className="text-slate-500">
                    Cash: {fmtMoney(a.cash_balance)} / Initial: {fmtMoney(a.initial_capital)}
                  </span>
                </button>
                <button
                  onClick={() => deleteAccount(a)}
                  title={`Delete ${a.name}`}
                  className="rounded border border-red-200 px-1.5 py-0.5 text-[11px] text-red-500 hover:bg-red-50"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {selected && (
        <Card
          title={selected.name}
          subtitle={`Equity: ${fmtMoney(selected.equity)} | Unrealized: ${fmtMoney(selected.unrealized_pnl)}`}
          actions={
            <div className="flex items-center gap-2">
              <Badge tone="green">Paper</Badge>
              <button
                onClick={() => setSelected(null)}
                className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>
          }
        >
          <div className="mb-4 grid gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-400">Cash</p>
              <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-800">
                {fmtMoney(selected.cash_balance)}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-400">Equity</p>
              <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-800">
                {fmtMoney(selected.equity)}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-400">Open Positions</p>
              <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-800">
                {selected.open_positions.length}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-slate-400">Total Orders</p>
              <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-800">
                {selected.recent_orders.length}
              </p>
            </div>
          </div>

          {selected.open_positions.length > 0 && (
            <>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Open Positions
              </h3>
              <div className="mb-3 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-slate-400">
                    <tr>
                      <th className="py-1 pr-3">Direction</th>
                      <th className="py-1 pr-3">Qty</th>
                      <th className="py-1 pr-3">Entry</th>
                      <th className="py-1 pr-3">Last</th>
                      <th className="py-1 pr-3">Unrealized</th>
                      <th className="py-1 pr-3">Stop</th>
                      <th className="py-1">Target</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {selected.open_positions.map((p) => (
                      <tr key={p.id} className="border-t border-slate-100">
                        <td className="py-1 pr-3">
                          <Badge tone={p.direction === "long" ? "green" : "amber"}>{p.direction}</Badge>
                        </td>
                        <td className="py-1 pr-3">{p.quantity}</td>
                        <td className="py-1 pr-3">{p.entry_price}</td>
                        <td className="py-1 pr-3">{p.last_close}</td>
                        <td
                          className={`py-1 pr-3 font-medium ${(p.unrealized_pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"}`}
                        >
                          {p.unrealized_pnl !== undefined ? fmtMoney(p.unrealized_pnl) : "-"}
                        </td>
                        <td className="py-1 pr-3">{p.stop_price ?? "-"}</td>
                        <td className="py-1">{p.target_price ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {selected.closed_positions.length > 0 && (
            <>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Closed Positions
              </h3>
              <div className="mb-3 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-slate-400">
                    <tr>
                      <th className="py-1 pr-3">Direction</th>
                      <th className="py-1 pr-3">Qty</th>
                      <th className="py-1 pr-3">Entry</th>
                      <th className="py-1 pr-3">Exit</th>
                      <th className="py-1 pr-3">Reason</th>
                      <th className="py-1">Realized P&L</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {selected.closed_positions.map((p) => (
                      <tr key={p.id} className="border-t border-slate-100">
                        <td className="py-1 pr-3">
                          <Badge tone={p.direction === "long" ? "green" : "amber"}>{p.direction}</Badge>
                        </td>
                        <td className="py-1 pr-3">{p.quantity}</td>
                        <td className="py-1 pr-3">{p.entry_price}</td>
                        <td className="py-1 pr-3">{p.exit_price ?? "-"}</td>
                        <td className="py-1 pr-3">{p.exit_reason ?? "-"}</td>
                        <td
                          className={`py-1 font-medium ${(p.realized_pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"}`}
                        >
                          {p.realized_pnl !== undefined ? fmtMoney(p.realized_pnl) : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {selected.recent_orders.length > 0 && (
            <>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Recent Orders
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-slate-400">
                    <tr>
                      <th className="py-1 pr-3">Time</th>
                      <th className="py-1 pr-3">Side</th>
                      <th className="py-1 pr-3">Qty</th>
                      <th className="py-1 pr-3">Price</th>
                      <th className="py-1">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {selected.recent_orders.slice(0, 20).map((o) => (
                      <tr key={o.id} className="border-t border-slate-100">
                        <td className="py-1 pr-3 text-slate-500">
                          {o.created_at ? new Date(o.created_at).toLocaleString() : "-"}
                        </td>
                        <td className="py-1 pr-3">
                          <Badge tone={o.side === "BUY" ? "green" : "red"}>{o.side}</Badge>
                        </td>
                        <td className="py-1 pr-3">{o.quantity}</td>
                        <td className="py-1 pr-3">{o.filled_price}</td>
                        <td className="py-1">{o.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
