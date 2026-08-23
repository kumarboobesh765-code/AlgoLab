"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ForwardTestRun,
  type ForwardTestCreate,
  type PaperAccount,
  type Strategy,
  type TickResult,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

function fmtMoney(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export default function ForwardTestPage() {
  const [runs, setRuns] = useState<ForwardTestRun[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tickingId, setTickingId] = useState<string | null>(null);
  const [tickResult, setTickResult] = useState<TickResult | null>(null);

  const refresh = useCallback(() => {
    api<ForwardTestRun[]>("/forward-tests")
      .then(setRuns)
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load forward tests"));
    api<Strategy[]>("/strategies")
      .then((all) => {
        const withDef = all.filter((s) => s.definition !== null);
        setStrategies(withDef);
        if (withDef.length > 0) setStrategyId((cur) => cur || withDef[0].id);
      })
      .catch(() => {});
    api<PaperAccount[]>("/paper/accounts")
      .then((accs) => {
        setAccounts(accs);
        if (accs.length > 0) setAccountId((cur) => cur || accs[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function createRun() {
    if (!strategyId || !accountId) return;
    setCreating(true);
    setError(null);
    try {
      const run = await api<ForwardTestRun>("/forward-tests", {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId, account_id: accountId } as ForwardTestCreate),
      });
      setRuns([run, ...runs]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start forward test");
    } finally {
      setCreating(false);
    }
  }

  async function tick(runId: string) {
    setTickingId(runId);
    setError(null);
    try {
      const result = await api<TickResult>(`/forward-tests/${runId}/tick`, { method: "POST" });
      setTickResult(result);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tick failed");
    } finally {
      setTickingId(null);
    }
  }

  async function transition(runId: string, action: "pause" | "resume" | "stop") {
    try {
      await api<ForwardTestRun>(`/forward-tests/${runId}/${action}`, { method: "POST" });
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : `${action} failed`);
    }
  }

  const running = runs.filter((r) => r.status === "running");
  const paused = runs.filter((r) => r.status === "paused");
  const stopped = runs.filter((r) => r.status === "stopped");
  const strategyName = (id: string) =>
    strategies.find((s) => s.id === id)?.name ?? `Strategy ${id.slice(0, 8)}…`;

  return (
    <div className="space-y-4">
      {loadError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {loadError}
        </p>
      )}
      <Card
        title="Start a Forward Test"
        subtitle="Run a strategy against a paper account on stored candles. Tick processes new bars since the last tick."
      >
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="block text-xs font-medium text-slate-500">
            Strategy
            <select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            >
              {strategies.length === 0 && <option value="">No strategies with definitions</option>}
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} (v{s.current_version})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Paper Account
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            >
              {accounts.length === 0 && <option value="">Create an account first</option>}
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({fmtMoney(a.cash_balance)})
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button
              onClick={createRun}
              disabled={creating || !strategyId || !accountId}
              className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
            >
              {creating ? "Starting..." : "Start"}
            </button>
          </div>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </Card>

      <Card title="Active Tests" subtitle="Running forward tests — click Tick to process new bars.">
        {running.length === 0 && paused.length === 0 ? (
          <p className="text-xs text-slate-500">No active forward tests.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {[...running, ...paused].map((r) => (
              <li key={r.id}>
                <div className="flex items-center justify-between gap-3 py-2 text-xs">
                  <span className="flex items-center gap-2">
                    <Badge tone={r.status === "running" ? "green" : "amber"}>{r.status}</Badge>
                    <span className="font-medium text-slate-700">
                      {strategyName(r.strategy_id)} · v{r.version_number}
                    </span>
                    <span className="text-slate-400">{new Date(r.started_at).toLocaleString()}</span>
                  </span>
                  <span className="flex gap-2">
                    {r.status === "running" && (
                      <>
                        <button
                          onClick={() => tick(r.id)}
                          disabled={tickingId === r.id}
                          className="rounded border border-sky-200 px-2 py-0.5 text-sky-600 hover:bg-sky-50 disabled:opacity-50"
                        >
                          {tickingId === r.id ? "Ticking…" : "Tick"}
                        </button>
                        <button
                          onClick={() => transition(r.id, "pause")}
                          className="rounded border border-amber-200 px-2 py-0.5 text-amber-600 hover:bg-amber-50"
                        >
                          Pause
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm("Stop this forward test? Any open position will be force-closed at the last price.")) {
                              transition(r.id, "stop");
                            }
                          }}
                          className="rounded border border-red-200 px-2 py-0.5 text-red-600 hover:bg-red-50"
                        >
                          Stop
                        </button>
                      </>
                    )}
                    {r.status === "paused" && (
                      <>
                        <button
                          onClick={() => transition(r.id, "resume")}
                          className="rounded border border-green-200 px-2 py-0.5 text-green-600 hover:bg-green-50"
                        >
                          Resume
                        </button>
                        <button
                          onClick={() => transition(r.id, "stop")}
                          className="rounded border border-red-200 px-2 py-0.5 text-red-600 hover:bg-red-50"
                        >
                          Stop
                        </button>
                      </>
                    )}
                  </span>
                </div>
                {r.last_message && (
                  <p className="pb-2 text-[11px] text-slate-500">{r.last_message}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {tickResult && (
        <Card title="Last Tick Result" subtitle={`${tickResult.bars_processed} bars processed`}>
          {tickResult.message && <p className="mb-2 text-xs text-slate-600">{tickResult.message}</p>}
          {tickResult.fills.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-slate-400">
                  <tr>
                    <th className="py-1 pr-3">Side</th>
                    <th className="py-1 pr-3">Qty</th>
                    <th className="py-1 pr-3">Price</th>
                    <th className="py-1 pr-3">Reason</th>
                    <th className="py-1">P&L</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {tickResult.fills.map((f, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="py-1 pr-3">
                        <Badge tone={f.side === "BUY" ? "green" : "red"}>{f.side}</Badge>
                      </td>
                      <td className="py-1 pr-3">{f.quantity}</td>
                      <td className="py-1 pr-3">{f.price}</td>
                      <td className="py-1 pr-3">{f.reason}</td>
                      <td className={`py-1 ${f.pnl !== undefined && f.pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                        {f.pnl !== undefined ? fmtMoney(f.pnl) : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tickResult.open_position && (
            <div className="mt-2 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
              <span className="font-medium">Open Position:</span>{" "}
              {tickResult.open_position.direction} {tickResult.open_position.quantity} @ {tickResult.open_position.entry_price}
            </div>
          )}
        </Card>
      )}

      <Card title="Stopped Tests" subtitle="Completed forward tests (positions force-closed).">
        {stopped.length === 0 ? (
          <p className="text-xs text-slate-500">No stopped tests yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {stopped.map((r) => (
              <li key={r.id} className="py-2 text-xs">
                <span className="flex items-center gap-2">
                  <Badge tone="red">stopped</Badge>
                  <span className="text-slate-500">
                    {strategyName(r.strategy_id)} stopped {r.stopped_at ? new Date(r.stopped_at).toLocaleString() : "-"}
                  </span>
                </span>
                {r.last_message && <p className="mt-1 text-[11px] text-slate-400">{r.last_message}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
