"use client";

import { useState } from "react";
import { api, type DeployOut, type Strategy } from "@/lib/api";

const BROKERS = [
  { value: "mock", label: "Mock (Virtual)" },
  { value: "zerodha", label: "Zerodha" },
  { value: "upstox", label: "Upstox" },
  { value: "angelone", label: "Angel One" },
  { value: "dhan", label: "Dhan" },
  { value: "fyers", label: "Fyers" },
  { value: "icici", label: "ICICI Direct" },
  { value: "5paisa", label: "5Paisa" },
];

const SEGMENTS = [
  { value: "OPTIONS", label: "Options" },
  { value: "EQUITY", label: "Equity" },
  { value: "FUTURES", label: "Futures" },
];

interface DeployModalProps {
  strategy: Strategy;
  mode: "paper" | "live";
  onClose: () => void;
  onDeployed: (d: DeployOut) => void;
}

export function DeployModal({ strategy, mode, onClose, onDeployed }: DeployModalProps) {
  const [broker, setBroker] = useState("mock");
  const [segment, setSegment] = useState("OPTIONS");
  const [name, setName] = useState(
    `${strategy.name} ${new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}`,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function deploy() {
    setLoading(true);
    setError(null);
    try {
      const result = await api<DeployOut>("/execution/deploy", {
        method: "POST",
        body: JSON.stringify({
          strategy_id: strategy.id,
          broker,
          mode,
          name,
          segment,
          exchange: "NSE",
        }),
      });
      onDeployed(result);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deploy failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900">
            Deploy strategy
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <p className="mt-1 text-xs text-slate-500">
          Registering{" "}
          <span className="font-medium text-slate-700">{strategy.name}</span>{" "}
          {mode === "paper" ? "as a paper-trading deployment" : "for live execution"}.
        </p>

        {mode === "live" && (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
            Live mode will place real orders. Ensure your SEBI algo registration (CIR/2025/0000013)
            is complete and your broker is connected.
          </div>
        )}

        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-slate-500">
            Deployment name
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800"
              placeholder="My straddle deployment"
            />
          </label>

          <label className="block text-xs font-medium text-slate-500">
            Broker
            <select
              value={broker}
              onChange={(e) => setBroker(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800"
            >
              {BROKERS.map((b) => (
                <option key={b.value} value={b.value}>
                  {b.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs font-medium text-slate-500">
            Segment
            <select
              value={segment}
              onChange={(e) => setSegment(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800"
            >
              {SEGMENTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <p className="mt-3 text-xs text-red-600">{error}</p>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            onClick={deploy}
            disabled={loading || !name.trim()}
            className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Deploying..." : `Deploy ${mode === "paper" ? "to paper" : "live"}`}
          </button>
        </div>
      </div>
    </div>
  );
}
