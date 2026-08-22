"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Instrument, PreviewResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { emptyDefinition } from "@/lib/builders";
import type { StrategyDefinitionV1 } from "@/lib/builders";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

interface ScanRow {
  symbol: string;
  resp?: PreviewResponse;
  err?: string;
}

interface Preset {
  id: string;
  label: string;
  build: (timeframe: string, symbol: string) => StrategyDefinitionV1;
  /** which indicator output to surface as the "value" column */
  tail: { id: string; output: string };
}

const PRESETS: Preset[] = [
  {
    id: "rsi_os",
    label: "RSI(14) oversold (< 30)",
    tail: { id: "r", output: "rsi" },
    build: (tf, sym) => {
      const d = emptyDefinition();
      d.timeframe = tf;
      d.instrument = { ...d.instrument, symbol: sym };
      d.indicators = [{ id: "r", type: "RSI", params: { length: 14 } }];
      d.entry = {
        logic: "ALL",
        conditions: [
          {
            left: { kind: "indicator", ref: "r.rsi" },
            op: "LT",
            right: { kind: "constant", value: 30 },
          },
        ],
      };
      return d;
    },
  },
  {
    id: "rsi_ob",
    label: "RSI(14) overbought (> 70)",
    tail: { id: "r", output: "rsi" },
    build: (tf, sym) => {
      const d = emptyDefinition();
      d.timeframe = tf;
      d.instrument = { ...d.instrument, symbol: sym };
      d.indicators = [{ id: "r", type: "RSI", params: { length: 14 } }];
      d.entry = {
        logic: "ALL",
        conditions: [
          {
            left: { kind: "indicator", ref: "r.rsi" },
            op: "GT",
            right: { kind: "constant", value: 70 },
          },
        ],
      };
      return d;
    },
  },
  {
    id: "sma_trend",
    label: "Close above SMA(50)",
    tail: { id: "s", output: "sma" },
    build: (tf, sym) => {
      const d = emptyDefinition();
      d.timeframe = tf;
      d.instrument = { ...d.instrument, symbol: sym };
      d.indicators = [{ id: "s", type: "SMA", params: { length: 50 } }];
      d.entry = {
        logic: "ALL",
        conditions: [
          {
            left: { kind: "price", price: "close" },
            op: "GT",
            right: { kind: "indicator", ref: "s.sma" },
          },
        ],
      };
      return d;
    },
  },
  {
    id: "ema_cross",
    label: "EMA(9) crosses above EMA(21)",
    tail: { id: "e9", output: "ema" },
    build: (tf, sym) => {
      const d = emptyDefinition();
      d.timeframe = tf;
      d.instrument = { ...d.instrument, symbol: sym };
      d.indicators = [
        { id: "e9", type: "EMA", params: { length: 9 } },
        { id: "e21", type: "EMA", params: { length: 21 } },
      ];
      d.entry = {
        logic: "ALL",
        conditions: [
          {
            left: { kind: "indicator", ref: "e9.ema" },
            op: "CROSS_ABOVE",
            right: { kind: "indicator", ref: "e21.ema" },
          },
        ],
      };
      return d;
    },
  },
  {
    id: "macd_bull",
    label: "MACD histogram crosses above 0",
    tail: { id: "m", output: "histogram" },
    build: (tf, sym) => {
      const d = emptyDefinition();
      d.timeframe = tf;
      d.instrument = { ...d.instrument, symbol: sym };
      d.indicators = [
        { id: "m", type: "MACD", params: { fast: 12, slow: 26, signal: 9 } },
      ];
      d.entry = {
        logic: "ALL",
        conditions: [
          {
            left: { kind: "indicator", ref: "m.histogram" },
            op: "CROSS_ABOVE",
            right: { kind: "constant", value: 0 },
          },
        ],
      };
      return d;
    },
  },
];

export default function ScannerPage() {
  const auth = useAuth();
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [presetId, setPresetId] = useState(PRESETS[0].id);
  const [timeframe, setTimeframe] = useState("5m");
  const [bars, setBars] = useState(500);
  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<ScanRow[] | null>(null);

  useEffect(() => {
    if (!auth.user) return;
    api<Instrument[]>("/data/instruments")
      .then((list) => {
        setInstruments(list);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [auth.user]);

  const symbols = useMemo(() => {
    const idx = instruments.filter((i) => i.segment === "index");
    return [...new Set(idx.map((i) => i.symbol))].sort();
  }, [instruments]);

  function resync() {
    setError(null);
    setLoading(true);
    api<{ synced: number }>("/data/instruments/sync", { method: "POST" })
      .then(() => api<Instrument[]>("/data/instruments"))
      .then((list) => {
        setInstruments(list);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }

  function scan() {
    if (symbols.length === 0 || scanning) return;
    setScanning(true);
    setResults(null);
    setError(null);
    const preset = PRESETS.find((p) => p.id === presetId)!;
    const rows: ScanRow[] = [];
    (async () => {
      for (const symbol of symbols) {
        try {
          const def = preset.build(timeframe, symbol);
          const resp = await api<PreviewResponse>(
            `/quant/preview?bars=${bars}`,
            { method: "POST", body: JSON.stringify(def) },
          );
          rows.push({ symbol, resp });
        } catch (e) {
          rows.push({ symbol, err: e instanceof Error ? e.message : String(e) });
        }
      }
      setResults(rows);
      setScanning(false);
    })();
  }

  if (!auth.user) {
    return <p className="text-sm text-slate-500">Sign in to use the scanner.</p>;
  }
  if (loading && instruments.length === 0)
    return <p className="text-sm text-slate-500">Loading instruments…</p>;

  const matches = results?.filter((r) => r.resp?.last_bar_entry_signal).length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Market Scanner</h2>
        <p className="text-sm text-slate-500">
          Screen instruments against a condition template using the quant engine preview.
        </p>
      </div>

      {symbols.length === 0 ? (
        <Card title="No instruments" subtitle="The scanner needs the instrument master synced first.">
          <button
            onClick={resync}
            disabled={loading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Sync instrument master
          </button>
        </Card>
      ) : (
        <>
          <Card title="Scan configuration" subtitle={`${symbols.length} instrument(s): ${symbols.join(", ")}`}>
            <div className="flex flex-wrap items-end gap-4">
              <label className="block text-xs">
                <span className="mb-1 block font-medium text-slate-600">Condition</span>
                <select
                  value={presetId}
                  onChange={(e) => setPresetId(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  {PRESETS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs">
                <span className="mb-1 block font-medium text-slate-600">Timeframe</span>
                <select
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  {["1m", "5m", "15m", "30m", "1h", "1d"].map((tf) => (
                    <option key={tf}>{tf}</option>
                  ))}
                </select>
              </label>
              <label className="block text-xs">
                <span className="mb-1 block font-medium text-slate-600">Bars</span>
                <select
                  value={bars}
                  onChange={(e) => setBars(Number(e.target.value))}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  {[200, 500, 1000].map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={scan}
                disabled={scanning}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {scanning ? "Scanning…" : "Run scan"}
              </button>
              {scanning && (
                <span className="text-xs text-slate-500">Evaluating {symbols.length} instruments…</span>
              )}
            </div>
          </Card>

          {error && <p className="text-sm text-red-600">{error}</p>}

          {results && (
            <Card
              title="Scan results"
              subtitle={`${matches} of ${results.length} matched on the latest bar`}
              actions={
                <div className="flex items-center gap-2">
                  {results.some((r) => r.resp?.is_demo) && (
                    <Badge tone="amber">demo data</Badge>
                  )}
                  <Badge tone={matches > 0 ? "green" : "slate"}>
                    {matches > 0 ? `${matches} match(es)` : "no matches"}
                  </Badge>
                </div>
              }
            >
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-2 py-2">Symbol</th>
                      <th className="px-2 py-2 text-right">Bars</th>
                      <th className="px-2 py-2 text-right">Entry signals</th>
                      <th className="px-2 py-2 text-right">Exit signals</th>
                      <th className="px-2 py-2 text-right">{PRESETS.find((p) => p.id === presetId)!.tail.output} value</th>
                      <th className="px-2 py-2">Signal</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {results.map((row) => (
                      <tr key={row.symbol}>
                        <td className="px-2 py-2 font-medium text-slate-900">{row.symbol}</td>
                        {row.err ? (
                          <td colSpan={5} className="px-2 py-2 text-red-600">
                            {row.err}
                          </td>
                        ) : (
                          <>
                            <td className="px-2 py-2 text-right tabular-nums">
                              {row.resp!.bars_evaluated}
                            </td>
                            <td className="px-2 py-2 text-right tabular-nums">
                              {row.resp!.entry_signals}
                            </td>
                            <td className="px-2 py-2 text-right tabular-nums">
                              {row.resp!.exit_signals}
                            </td>
                            <td className="px-2 py-2 text-right tabular-nums">
                              {(() => {
                                const t = PRESETS.find((p) => p.id === presetId)!.tail;
                                const v = row.resp!.indicator_tail[t.id]?.[t.output];
                                return v == null ? "—" : Number(v).toFixed(2);
                              })()}
                            </td>
                            <td className="px-2 py-2">
                              {row.resp!.last_bar_entry_signal ? (
                                <Badge tone="green">MATCH</Badge>
                              ) : (
                                <span className="text-slate-400">—</span>
                              )}
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          <p className="text-xs text-slate-400">
            The scanner evaluates the most recent candles via the quant engine preview endpoint.
            With the demo provider this is synthetic data — wire a live provider for real screening.
          </p>
        </>
      )}
    </div>
  );
}
