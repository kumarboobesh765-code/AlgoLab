"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import {
  DEFAULT_SETTINGS,
  resetSettings,
  updateSettings,
  useAppSettings,
  type AppSettings,
} from "@/lib/settings";

export default function SettingsPage() {
  const auth = useAuth();
  const stored = useAppSettings();
  const [draft, setDraft] = useState<Partial<AppSettings>>({});
  const [saved, setSaved] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);

  const settings: AppSettings = { ...DEFAULT_SETTINGS, ...stored, ...draft };

  useEffect(() => {
    let cancelled = false;
    api<Health>("/health")
      .then((h) => {
        if (!cancelled) setHealth(h);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  function save() {
    updateSettings(settings);
    setDraft({});
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  function reset() {
    if (!window.confirm("Reset all settings to defaults?")) return;
    resetSettings();
    setDraft({});
  }

  if (!auth.user) {
    return <p className="text-sm text-slate-500">Connecting to the API…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Settings</h2>
        <p className="text-sm text-slate-500">
          Application preferences stored in your browser (v1 — server-side profile sync comes
          later).
        </p>
      </div>

      <Card title="Trading defaults" subtitle="Pre-fills backtest and paper-account forms">
        <div className="grid gap-4 md:grid-cols-3">
          <label className="block text-xs">
            <span className="mb-1 block font-medium text-slate-600">Default capital (₹)</span>
            <input
              type="number"
              min={1000}
              step={10000}
              value={settings.defaultCapital}
              onChange={(e) => setDraft({ ...draft, defaultCapital: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm tabular-nums focus:border-indigo-500 focus:outline-none"
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block font-medium text-slate-600">Costs per side (%)</span>
            <input
              type="number"
              min={0}
              max={5}
              step={0.01}
              value={settings.costsPct}
              onChange={(e) => setDraft({ ...draft, costsPct: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm tabular-nums focus:border-indigo-500 focus:outline-none"
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block font-medium text-slate-600">Default timeframe</span>
            <select
              value={settings.timeframe}
              onChange={(e) => setDraft({ ...draft, timeframe: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            >
              {["1m", "5m", "15m", "30m", "1h", "1d"].map((tf) => (
                <option key={tf}>{tf}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={save}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Save settings
          </button>
          <button
            onClick={reset}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Reset to defaults
          </button>
          {saved && <span className="text-xs font-medium text-emerald-600">Saved ✓</span>}
        </div>
      </Card>

      <Card title="API environment" subtitle="Live status reported by the backend">
        {!health ? (
          <p className="py-4 text-center text-sm text-slate-400">
            API unreachable or loading…
          </p>
        ) : (
          <dl className="space-y-2 text-xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <dt className="text-slate-500">Status</dt>
              <dd>
                <Badge tone={health.database === "ok" ? "green" : "red"}>{health.status}</Badge>
              </dd>
            </div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <dt className="text-slate-500">Market data provider</dt>
              <dd className="flex items-center gap-2">
                <span className="font-medium">{health.market_data_provider ?? "unknown"}</span>
                {health.market_data_is_demo && <Badge tone="amber">synthetic data</Badge>}
              </dd>
            </div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <dt className="text-slate-500">Environment</dt>
              <dd className="font-medium">{health.env ?? "—"}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">Trading mode</dt>
              <dd>
                <Badge tone="blue">{health.trading_mode.replace("_", " ")}</Badge>
              </dd>
            </div>
          </dl>
        )}
      </Card>

      <p className="text-xs text-slate-400">
        Provider selection (demo / Dhan) and alert channels (Telegram, webhook) are configured via
        environment variables on the API server — see .env.example.
      </p>
    </div>
  );
}
