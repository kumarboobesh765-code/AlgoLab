"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  type BacktestSummary,
  type Strategy,
  type StrategyReport,
  type VersionCompare,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

function fmtMoney(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function Metric({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: string;
  tone?: "slate" | "green" | "red";
}) {
  const toneClass =
    tone === "green"
      ? "text-emerald-600"
      : tone === "red"
        ? "text-red-600"
        : "text-slate-800";
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}

const COMPARE_ROWS: {
  key: keyof BacktestSummary;
  label: string;
  fmt: (v: number) => string;
  lowerIsBetter?: boolean;
}[] = [
  { key: "net_pnl", label: "Net P&L", fmt: (v) => fmtMoney(v) },
  { key: "return_pct", label: "Return %", fmt: (v) => `${v}%` },
  { key: "total_trades", label: "Trades", fmt: (v) => `${v}` },
  { key: "win_rate", label: "Win rate %", fmt: (v) => `${v}%` },
  { key: "profit_factor", label: "Profit factor", fmt: (v) => `${v}` },
  { key: "sharpe_ratio", label: "Sharpe", fmt: (v) => `${v}` },
  {
    key: "max_drawdown_pct",
    label: "Max drawdown %",
    fmt: (v) => `${v}%`,
    lowerIsBetter: true,
  },
];

export default function ReportsPage() {
  const { user, loading: authLoading } = useAuth();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [report, setReport] = useState<StrategyReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [v1, setV1] = useState("");
  const [v2, setV2] = useState("");
  const [comparing, setComparing] = useState(false);
  const [comparison, setComparison] = useState<VersionCompare | null>(null);

  useEffect(() => {
    if (!user) return;
    const wanted = new URLSearchParams(window.location.search).get("strategy");
    api<Strategy[]>("/strategies")
      .then((all) => {
        setStrategies(all);
        if (all.length > 0) {
          setSelectedId(
            (cur) =>
              cur ||
              (wanted && all.some((s) => s.id === wanted) ? wanted : all[0].id),
          );
        }
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load strategies"),
      );
  }, [user]);

  useEffect(() => {
    if (!user || !selectedId) return;
    let cancelled = false;
    api<StrategyReport>(`/strategies/${selectedId}/report`)
      .then((r) => {
        if (cancelled) return;
        setReport(r);
        setError(null);
        const vs = r.versions.map((x) => x.version).sort((a, b) => b - a);
        if (vs.length >= 2) {
          setV1(String(vs[vs.length - 1]));
          setV2(String(vs[0]));
        } else if (vs.length === 1) {
          setV1(String(vs[0]));
          setV2(String(vs[0]));
        }
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load report");
      });
    return () => {
      cancelled = true;
    };
  }, [user, selectedId]);

  async function runCompare() {
    if (!selectedId || !v1 || !v2) return;
    setComparing(true);
    setError(null);
    try {
      const c = await api<VersionCompare>(
        `/strategies/${selectedId}/compare?v1=${v1}&v2=${v2}`,
      );
      setComparison(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Compare failed");
    } finally {
      setComparing(false);
    }
  }

  if (!authLoading && !user) {
    return (
      <Card>
        <div className="py-10 text-center">
          <p className="text-sm text-slate-500">Sign in to view strategy reports.</p>
          <Link
            href="/login"
            className="mt-4 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Sign in
          </Link>
        </div>
      </Card>
    );
  }

  const s = report?.latest_backtest?.summary ?? null;
  const lb = report?.latest_backtest ?? null;

  return (
    <div className="space-y-4">
      <Card
        title="Reports"
        subtitle="Per-strategy performance overview, version history and version comparison."
        actions={
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="w-64 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          >
            {strategies.length === 0 && <option value="">No strategies yet</option>}
            {strategies.map((st) => (
              <option key={st.id} value={st.id}>
                {st.name} (v{st.current_version})
              </option>
            ))}
          </select>
        }
      >
        {!report ? (
          <p className="text-xs text-slate-500">
            {strategies.length === 0
              ? "Create a strategy first."
              : "Select a strategy to see its report."}
          </p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-1 text-xs">
              <p className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                {report.strategy.name}
                <StatusBadge status={report.strategy.status} />
              </p>
              <p className="text-slate-500">
                {report.strategy.exchange} · {report.strategy.underlying} ·{" "}
                {report.strategy.strategy_type}
              </p>
              <p className="text-slate-400">
                Created {new Date(report.strategy.created_at).toLocaleString()} ·{" "}
                {report.total_backtests} completed backtest(s)
              </p>
              <div className="flex flex-wrap gap-1 pt-1">
                {report.strategy.tags.map((t) => (
                  <span
                    key={t}
                    className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>

            <div className="lg:col-span-2">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Latest backtest {lb && `(v${lb.config?.["version"] ?? "?"}, ${lb.trades_count} trades)`}
              </h3>
              {lb && s ? (
                <>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Metric
                      label="Net P&L"
                      value={`${s.net_pnl >= 0 ? "+" : ""}${fmtMoney(s.net_pnl)}`}
                      tone={s.net_pnl >= 0 ? "green" : "red"}
                    />
                    <Metric
                      label="Return"
                      value={`${s.return_pct >= 0 ? "+" : ""}${s.return_pct}%`}
                      tone={s.return_pct >= 0 ? "green" : "red"}
                    />
                    <Metric label="Win rate" value={`${s.win_rate}%`} />
                    <Metric label="Max DD" value={`${s.max_drawdown_pct}%`} tone="red" />
                  </div>
                  <div className="mt-2 flex gap-3 text-xs">
                    <Link
                      href={`/replay?run=${lb.id}`}
                      className="font-medium text-sky-600 hover:underline"
                    >
                      Replay this run →
                    </Link>
                    <span className="text-slate-400">
                      {lb.created_at &&
                        new Date(lb.created_at).toLocaleString()}
                    </span>
                  </div>
                </>
              ) : (
                <p className="text-xs text-slate-500">
                  No completed backtests yet — run one from the Backtest page.
                </p>
              )}
            </div>
          </div>
        )}
      </Card>

      {report && (
        <Card title="Version history" subtitle={`${report.versions.length} version(s)`}>
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400">
              <tr>
                <th className="py-1 pr-3">Ver</th>
                <th className="py-1 pr-3">Created</th>
                <th className="py-1">Changelog</th>
              </tr>
            </thead>
            <tbody>
              {report.versions.map((v) => (
                <tr key={v.version} className="border-t border-slate-100">
                  <td className="py-1 pr-3 tabular-nums font-medium text-slate-700">
                    v{v.version}
                    {v.version === report.strategy.current_version && (
                      <span className="ml-1 text-[10px] text-emerald-600">current</span>
                    )}
                  </td>
                  <td className="py-1 pr-3 text-slate-500">
                    {new Date(v.created_at).toLocaleString()}
                  </td>
                  <td className="py-1 text-slate-600">{v.changelog ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {report && report.optimizations.length > 0 && (
        <Card
          title="Recent optimizations"
          subtitle="Latest completed optimization runs for this strategy"
        >
          <ul className="divide-y divide-slate-100 text-xs">
            {report.optimizations.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-2 py-2">
                <Badge tone="blue">{o.method}</Badge>
                <span className="text-slate-600">
                  target {o.target_metric} · {o.total_combinations} combos
                </span>
                {o.best_metrics != null && typeof o.best_metrics === "object" && (
                  <span className="tabular-nums text-slate-500">
                    best:{" "}
                    {Object.entries(o.best_metrics as Record<string, number>)
                      .slice(0, 3)
                      .map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(3) : v}`)
                      .join(", ")}
                  </span>
                )}
                <span className="ml-auto text-slate-400">
                  {new Date(o.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {report && report.versions.length >= 1 && (
        <Card
          title="Compare versions"
          subtitle="Side-by-side definition diff and backtest performance delta."
        >
          <div className="flex items-end gap-3">
            <label className="block text-xs font-medium text-slate-500">
              Version A
              <select
                value={v1}
                onChange={(e) => setV1(e.target.value)}
                className="mt-1 w-32 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              >
                {report.versions.map((x) => (
                  <option key={x.version} value={x.version}>
                    v{x.version}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-500">
              Version B
              <select
                value={v2}
                onChange={(e) => setV2(e.target.value)}
                className="mt-1 w-32 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              >
                {report.versions.map((x) => (
                  <option key={x.version} value={x.version}>
                    v{x.version}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={runCompare}
              disabled={comparing || !v1 || !v2}
              className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
            >
              {comparing ? "Comparing…" : "Compare"}
            </button>
          </div>

          {comparison && (
            <div className="mt-4 space-y-4">
              <table className="w-full text-left text-xs">
                <thead className="text-slate-400">
                  <tr>
                    <th className="py-1 pr-3">Metric</th>
                    <th className="py-1 pr-3">v{comparison.v1_version}</th>
                    <th className="py-1 pr-3">v{comparison.v2_version}</th>
                    <th className="py-1">Δ</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {COMPARE_ROWS.map((row) => {
                    const a = comparison.v1_backtest?.summary?.[row.key];
                    const b = comparison.v2_backtest?.summary?.[row.key];
                    if (typeof a !== "number" || typeof b !== "number") return null;
                    const delta = b - a;
                    const good = row.lowerIsBetter ? delta <= 0 : delta >= 0;
                    return (
                      <tr key={row.key} className="border-t border-slate-100">
                        <td className="py-1 pr-3 text-slate-600">{row.label}</td>
                        <td className="py-1 pr-3 text-slate-700">{row.fmt(a)}</td>
                        <td className="py-1 pr-3 text-slate-700">{row.fmt(b)}</td>
                        <td
                          className={`py-1 font-medium ${
                            delta === 0
                              ? "text-slate-400"
                              : good
                                ? "text-emerald-600"
                                : "text-red-600"
                          }`}
                        >
                          {delta > 0 ? "+" : ""}
                          {row.fmt(delta)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {comparison.v1_backtest?.summary == null &&
                comparison.v2_backtest?.summary == null && (
                  <p className="text-xs text-slate-500">
                    No completed backtests found for these versions — run both versions
                    to see the performance delta.
                  </p>
                )}

              <div className="grid gap-3 lg:grid-cols-2">
                {(
                  [
                    ["v" + comparison.v1_version, comparison.v1_definition],
                    ["v" + comparison.v2_version, comparison.v2_definition],
                  ] as const
                ).map(([label, defn]) => (
                  <div key={label}>
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Definition {label}
                    </p>
                    <pre className="max-h-72 overflow-auto rounded-md bg-slate-50 p-2 text-[11px] leading-relaxed text-slate-600 ring-1 ring-inset ring-slate-100">
                      {defn ? JSON.stringify(defn, null, 2) : "no definition"}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
