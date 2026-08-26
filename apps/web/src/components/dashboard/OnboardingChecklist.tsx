"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import {
  api,
  type BacktestRun,
  type DataStatus,
  type Strategy,
} from "@/lib/api";

const STORAGE_KEY = "sl_onboarding_dismissed";

type Listener = () => void;
let listeners: Listener[] = [];

const dismissedStore = {
  subscribe(cb: Listener): () => void {
    listeners.push(cb);
    return () => {
      listeners = listeners.filter((l) => l !== cb);
    };
  },
  get(): boolean {
    if (typeof window === "undefined") return true;
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return true;
    }
  },
  set(): void {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* private mode */
    }
    listeners.forEach((l) => l());
  },
};

export function OnboardingChecklist() {
  const dismissed = useSyncExternalStore(
    dismissedStore.subscribe,
    dismissedStore.get,
    () => true,
  );
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [runs, setRuns] = useState<BacktestRun[] | null>(null);
  const [dataStatus, setDataStatus] = useState<DataStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<Strategy[]>("/strategies")
      .then((s) => {
        if (!cancelled) setStrategies(s);
      })
      .catch(() => {});
    api<BacktestRun[]>("/backtests")
      .then((rs) => {
        if (!cancelled) setRuns(rs);
      })
      .catch(() => {});
    api<DataStatus>("/data/status")
      .then((st) => {
        if (!cancelled) setDataStatus(st);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (dismissed || strategies === null || runs === null) return null;

  const hasData = Object.values(dataStatus?.candle_counts ?? {}).some((n) => n > 0);
  const hasStrategy = strategies.length > 0;
  const hasRun = runs.length > 0;

  if (hasData && hasStrategy && hasRun) return null; // all done — hide automatically

  const steps = [
    {
      label: "Ingest market data",
      detail: "Sync instruments and pull demo NIFTY candles in the Data Manager",
      href: "/tools/data-manager",
      done: hasData,
    },
    {
      label: "Create your first strategy",
      detail: "Use the Visual Builder — no code needed",
      href: "/builder/visual",
      done: hasStrategy,
    },
    {
      label: "Run your first backtest",
      detail: "See metrics, equity curve and every trade",
      href: "/backtest",
      done: hasRun,
    },
  ];

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-800">Get started with StrategyLab</p>
          <p className="mt-0.5 text-xs text-slate-500">
            Three quick steps to your first backtested strategy.
          </p>
        </div>
        <button
          onClick={dismissedStore.set}
          className="rounded p-1 text-slate-400 hover:bg-white hover:text-slate-600"
          aria-label="Dismiss onboarding"
        >
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" />
          </svg>
        </button>
      </div>

      <ol className="mt-4 space-y-2.5">
        {steps.map((s, i) => (
          <li key={s.label}>
            <Link
              href={s.href}
              className={`flex items-center gap-3 rounded-lg border p-3 transition-colors ${
                s.done
                  ? "border-green-200 bg-green-50"
                  : "border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/40"
              }`}
            >
              <span
                className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  s.done ? "bg-green-500 text-white" : "bg-slate-100 text-slate-500"
                }`}
              >
                {s.done ? "✓" : i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className={`block text-[13px] font-medium ${s.done ? "text-green-800" : "text-slate-700"}`}>
                  {s.label}
                </span>
                <span className="block truncate text-[11px] text-slate-400">{s.detail}</span>
              </span>
              {!s.done && (
                <svg className="h-4 w-4 flex-shrink-0 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
