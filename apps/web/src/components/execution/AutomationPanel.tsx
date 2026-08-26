"use client";

import { useEffect, useState } from "react";
import { api, type Strategy } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

interface AutomationState {
  strategy_id: string;
  broker: string;
  mode: string;
  runs: number;
  orders_placed: number;
  direction: string | null;
  last_message: string;
  last_run_at: string | null;
}

export function AutomationPanel() {
  const { showToast } = useToast();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [mode, setMode] = useState<"paper" | "confirm" | "live">("paper");
  const [states, setStates] = useState<AutomationState[]>([]);
  const [busy, setBusy] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);

  async function refresh() {
    try {
      const [all, strats] = await Promise.all([
        api<AutomationState[]>("/automation"),
        api<Strategy[]>("/strategies"),
      ]);
      setStates(all);
      setStrategies(strats.filter((s) => s.definition));
      setStrategyId((cur) => cur || strats.find((s) => s.definition)?.id || "");
    } catch {
      /* panel is optional sugar */
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function start() {
    if (!strategyId) return;
    setBusy(true);
    try {
      await api("/automation/start", {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId, broker: "mock", mode }),
      });
      showToast({ type: "success", title: "Automation started", message: `Mode: ${mode}` });
      await refresh();
    } catch (e) {
      showToast({ type: "error", title: "Start failed", message: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  }

  async function stop(id: string) {
    setBusy(true);
    try {
      await api(`/automation/${id}/stop`, { method: "POST" });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function runOnce(id: string) {
    setBusy(true);
    try {
      const r = await api<{ message?: string; actions?: string[] }>(`/automation/${id}/run-once`, { method: "POST" });
      setLastRun(r.message ?? null);
      showToast({
        type: r.actions?.length ? "success" : "info",
        title: r.actions?.length ? "Signal acted on" : "No signal",
        message: r.message,
      });
      await refresh();
    } catch (e) {
      showToast({ type: "error", title: "Run failed", message: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Evaluates the strategy on the latest stored candles and routes orders through the OMS
        (risk caps, OPS limiter and confirm-mode all apply). Run once manually or leave armed.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <label className="block text-xs font-medium text-slate-500">
          Strategy
          <select
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="mt-1 block w-64 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-500">
          Mode
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}
            className="mt-1 block w-36 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            <option value="paper">Paper</option>
            <option value="confirm">Confirm each</option>
            <option value="live">Live</option>
          </select>
        </label>
        <button
          onClick={start}
          disabled={busy || !strategyId}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Arm automation
        </button>
      </div>

      {lastRun && (
        <p className="rounded-md bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-600 ring-1 ring-inset ring-slate-200">
          {lastRun}
        </p>
      )}

      {states.length === 0 ? (
        <p className="py-4 text-center text-xs text-slate-400">No automations armed yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[12px]">
            <thead>
              <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                <th className="pb-2 pr-3 font-medium">Strategy</th>
                <th className="pb-2 pr-3 font-medium">Mode</th>
                <th className="pb-2 pr-3 font-medium">Runs</th>
                <th className="pb-2 pr-3 font-medium">Orders</th>
                <th className="pb-2 pr-3 font-medium">Position</th>
                <th className="pb-2 pr-3 font-medium">Last message</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {states.map((a) => {
                const name = strategies.find((s) => s.id === a.strategy_id)?.name ?? a.strategy_id.slice(0, 8);
                return (
                  <tr key={a.strategy_id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2 pr-3 font-medium text-slate-700">{name}</td>
                    <td className="py-2 pr-3 capitalize text-slate-500">{a.mode}</td>
                    <td className="py-2 pr-3 tabular-nums text-slate-500">{a.runs}</td>
                    <td className="py-2 pr-3 tabular-nums text-slate-500">{a.orders_placed}</td>
                    <td className="py-2 pr-3 text-slate-500">{a.direction ?? "flat"}</td>
                    <td className="max-w-[220px] truncate py-2 pr-3 text-[11px] text-slate-400">{a.last_message}</td>
                    <td className="py-2">
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => runOnce(a.strategy_id)}
                          disabled={busy}
                          className="rounded border border-blue-200 px-2 py-0.5 text-[11px] text-blue-600 hover:bg-blue-50 disabled:opacity-50"
                        >
                          Run once
                        </button>
                        <button
                          onClick={() => stop(a.strategy_id)}
                          disabled={busy}
                          className="rounded border border-red-200 px-2 py-0.5 text-[11px] text-red-500 hover:bg-red-50 disabled:opacity-50"
                        >
                          Stop
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
