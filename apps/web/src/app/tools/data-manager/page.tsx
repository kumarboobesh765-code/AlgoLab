"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type DataIssue,
  type DataStatus,
  type IngestResult,
  type Instrument,
  type QualityReport,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

const INTERVALS = ["1m", "5m", "15m", "30m", "1h", "1d"];

function todayISO(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const ISSUE_TONES: Record<string, "red" | "amber" | "slate"> = {
  empty: "red",
  invalid_ohlc: "red",
  duplicate_timestamp: "amber",
  abnormal_jump: "amber",
  misaligned_timestamp: "amber",
  outside_market_hours: "amber",
};

function IssueList({ issues }: { issues: DataIssue[] }) {
  if (issues.length === 0) {
    return <p className="text-xs text-emerald-600">No data-quality issues detected.</p>;
  }
  return (
    <ul className="space-y-1.5">
      {issues.map((i, idx) => (
        <li key={idx} className="flex items-start gap-2 text-xs">
          <Badge tone={ISSUE_TONES[i.type] ?? "slate"}>{i.type}</Badge>
          <span className="text-slate-600">
            {i.detail}
            {i.examples.length > 0 && (
              <span className="ml-1 text-slate-400">e.g. {i.examples.slice(0, 3).join(", ")}</span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function DataManagerPage() {
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [search, setSearch] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ingestion form
  const [symbol, setSymbol] = useState("NIFTY");
  const [interval, setInterval] = useState("5m");
  const [start, setStart] = useState(todayISO(-7));
  const [end, setEnd] = useState(todayISO(-1));
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null);

  // quality
  const [qualitySymbol, setQualitySymbol] = useState("NIFTY");
  const [qualityInterval, setQualityInterval] = useState("5m");
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [checkingQuality, setCheckingQuality] = useState(false);

  const refreshStatus = useCallback(() => {
    api<DataStatus>("/data/status")
      .then((s) => {
        setStatus(s);
        setError(null);
      })
      .catch((e: Error) => setError(`Could not load data status — ${e.message}`));
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const syncInstruments = async () => {
    setSyncing(true);
    setMessage(null);
    setError(null);
    try {
      const r = await api<{ received: number; inserted_or_updated: number; provider: string }>(
        "/data/instruments/sync",
        { method: "POST" },
      );
      setMessage(`Instrument master synced from ${r.provider}: ${r.inserted_or_updated} of ${r.received} rows stored.`);
      const list = await api<Instrument[]>("/data/instruments");
      setInstruments(list);
      refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    api<Instrument[]>("/data/instruments")
      .then(setInstruments)
      .catch(() => {
        /* empty until first sync */
      });
  }, []);

  const runIngest = async () => {
    setIngesting(true);
    setIngestResult(null);
    setMessage(null);
    setError(null);
    try {
      const r = await api<IngestResult>("/data/history/ingest", {
        method: "POST",
        body: JSON.stringify({ symbol, interval, start, end }),
      });
      setIngestResult(r);
      refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ingestion failed");
    } finally {
      setIngesting(false);
    }
  };

  const runQuality = async () => {
    setCheckingQuality(true);
    setQuality(null);
    setError(null);
    try {
      const r = await api<QualityReport>(
        `/data/quality/${encodeURIComponent(qualitySymbol)}?interval=${qualityInterval}&days=30`,
      );
      setQuality(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Quality check failed");
    } finally {
      setCheckingQuality(false);
    }
  };

  const filtered = instruments.filter(
    (i) =>
      !search ||
      i.symbol.toLowerCase().includes(search.toLowerCase()) ||
      (i.name ?? "").toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-4">
      {message && (
        <p className="rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-700 ring-1 ring-inset ring-blue-200">
          {message}
        </p>
      )}
      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}

      {/* Status overview */}
      <Card title="Data status">
        {!status ? (
          <p className="text-xs text-slate-400">Loading…</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            <div>
              <p className="text-[10px] uppercase tracking-wide text-slate-400">Instruments</p>
              <p className="text-lg font-semibold text-slate-800">{status.instruments}</p>
            </div>
            {Object.entries(status.candle_counts).map(([seg, count]) => (
              <div key={seg}>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">{seg} candles</p>
                <p className="text-lg font-semibold text-slate-800">{count.toLocaleString("en-IN")}</p>
                <p className="text-[10px] text-slate-400">
                  latest: {status.latest_candle_utc[seg] ? status.latest_candle_utc[seg]!.slice(0, 16).replace("T", " ") : "—"}
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Instruments */}
      <Card
        title="Instrument master"
        subtitle="Syncs the Dhan master list (demo provider stores its built-in indices)"
        actions={
          <button
            onClick={syncInstruments}
            disabled={syncing}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        }
      >
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search symbol or name…"
          className="mb-3 w-full max-w-xs rounded-md border border-slate-200 px-3 py-1.5 text-xs outline-none focus:border-blue-500"
        />
        {filtered.length === 0 ? (
          <p className="py-6 text-center text-xs text-slate-400">
            No instruments yet — click “Sync now”.
          </p>
        ) : (
          <div className="max-h-72 overflow-auto rounded-md border border-slate-100">
            <table className="w-full text-left text-[12px]">
              <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Symbol</th>
                  <th className="px-3 py-1.5 font-medium">Name</th>
                  <th className="px-3 py-1.5 font-medium">Exchange</th>
                  <th className="px-3 py-1.5 font-medium">Segment</th>
                  <th className="px-3 py-1.5 font-medium">Security ID</th>
                  <th className="px-3 py-1.5 text-right font-medium">Lot</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 100).map((i) => (
                  <tr key={i.id} className="border-t border-slate-50">
                    <td className="px-3 py-1.5 font-medium text-slate-700">{i.symbol}</td>
                    <td className="px-3 py-1.5 text-slate-500">{i.name ?? "—"}</td>
                    <td className="px-3 py-1.5 text-slate-500">{i.exchange}</td>
                    <td className="px-3 py-1.5"><Badge tone="slate">{i.segment}</Badge></td>
                    <td className="px-3 py-1.5 font-mono text-[11px] text-slate-500">{i.security_id}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{i.lot_size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length > 100 && (
              <p className="bg-slate-50 px-3 py-1 text-[10px] text-slate-400">
                Showing first 100 of {filtered.length}
              </p>
            )}
          </div>
        )}
      </Card>

      {/* Ingestion */}
      <Card title="Historical ingestion" subtitle="Fetches candles via the active market-data provider and upserts them">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-500">
            Symbol
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              className="mt-1 block w-28 rounded-md border border-slate-200 px-2 py-1.5 text-xs uppercase outline-none focus:border-blue-500"
            />
          </label>
          <label className="text-xs text-slate-500">
            Interval
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              className="mt-1 block w-24 rounded-md border border-slate-200 px-2 py-1.5 text-xs outline-none focus:border-blue-500"
            >
              {INTERVALS.map((iv) => (
                <option key={iv}>{iv}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">
            Start
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="mt-1 block w-36 rounded-md border border-slate-200 px-2 py-1.5 text-xs outline-none focus:border-blue-500"
            />
          </label>
          <label className="text-xs text-slate-500">
            End
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="mt-1 block w-36 rounded-md border border-slate-200 px-2 py-1.5 text-xs outline-none focus:border-blue-500"
            />
          </label>
          <button
            onClick={runIngest}
            disabled={ingesting || !symbol || !start || !end}
            className="rounded-md bg-emerald-600 px-4 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {ingesting ? "Ingesting…" : "Ingest"}
          </button>
        </div>

        {ingestResult && (
          <div className="mt-4 space-y-3 rounded-md border border-slate-100 p-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Fetched</p>
                <p className="text-base font-semibold text-slate-800">{ingestResult.fetched}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Upserted</p>
                <p className="text-base font-semibold text-slate-800">{ingestResult.inserted_or_updated}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Dupes in batch</p>
                <p className="text-base font-semibold text-slate-800">{ingestResult.duplicates_in_batch}</p>
              </div>
              {ingestResult.coverage && (
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">Coverage</p>
                  <Badge tone={ingestResult.coverage.status === "healthy" ? "green" : ingestResult.coverage.status === "warning" ? "amber" : "red"}>
                    {ingestResult.coverage.status} · {ingestResult.coverage.missing_pct.toFixed(1)}% missing
                  </Badge>
                </div>
              )}
            </div>
            <IssueList issues={ingestResult.issues} />
          </div>
        )}
      </Card>

      {/* Quality */}
      <Card title="Stored-data quality" subtitle="Validates candles already saved in the database">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-500">
            Symbol
            <input
              value={qualitySymbol}
              onChange={(e) => setQualitySymbol(e.target.value.toUpperCase())}
              className="mt-1 block w-28 rounded-md border border-slate-200 px-2 py-1.5 text-xs uppercase outline-none focus:border-blue-500"
            />
          </label>
          <label className="text-xs text-slate-500">
            Interval
            <select
              value={qualityInterval}
              onChange={(e) => setQualityInterval(e.target.value)}
              className="mt-1 block w-24 rounded-md border border-slate-200 px-2 py-1.5 text-xs outline-none focus:border-blue-500"
            >
              {INTERVALS.map((iv) => (
                <option key={iv}>{iv}</option>
              ))}
            </select>
          </label>
          <button
            onClick={runQuality}
            disabled={checkingQuality}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {checkingQuality ? "Checking…" : "Run quality check"}
          </button>
        </div>

        {quality && (
          <div className="mt-4 space-y-3 rounded-md border border-slate-100 p-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Candles checked</p>
                <p className="text-base font-semibold text-slate-800">{quality.candles_checked}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">First</p>
                <p className="text-xs font-medium text-slate-600">{quality.first?.slice(0, 16).replace("T", " ") ?? "—"}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Last</p>
                <p className="text-xs font-medium text-slate-600">{quality.last?.slice(0, 16).replace("T", " ") ?? "—"}</p>
              </div>
              {quality.coverage && (
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400">Coverage</p>
                  <Badge tone={quality.coverage.status === "healthy" ? "green" : quality.coverage.status === "warning" ? "amber" : "red"}>
                    {quality.coverage.status}
                  </Badge>
                </div>
              )}
            </div>
            <IssueList issues={quality.issues} />
          </div>
        )}
      </Card>
    </div>
  );
}
