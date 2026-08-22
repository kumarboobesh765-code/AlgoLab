"use client";

import type { PreviewResponse, ValidationResponse } from "@/lib/api";

export function ValidationPanel({
  validation,
  validating,
}: {
  validation: ValidationResponse | null;
  validating: boolean;
}) {
  if (validating) {
    return <p className="text-xs text-slate-400">Validating…</p>;
  }
  if (!validation) return null;

  return (
    <div className="space-y-1.5">
      {validation.valid ? (
        <p className="flex items-center gap-1.5 text-xs font-medium text-emerald-600">
          ✓ Definition is valid
          {validation.warnings.length > 0 && (
            <span className="font-normal text-amber-600">
              ({validation.warnings.length} warning{validation.warnings.length === 1 ? "" : "s"})
            </span>
          )}
        </p>
      ) : (
        <p className="text-xs font-medium text-red-600">
          ✕ {validation.errors.length} error{validation.errors.length === 1 ? "" : "s"}
        </p>
      )}
      {validation.errors.map((e, i) => (
        <p key={`e${i}`} className="rounded bg-red-50 px-2 py-1 text-[11px] text-red-700 ring-1 ring-inset ring-red-100">
          {e}
        </p>
      ))}
      {validation.warnings.map((w, i) => (
        <p key={`w${i}`} className="rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-100">
          ⚠ {w}
        </p>
      ))}
    </div>
  );
}

export function PreviewPanel({
  preview,
  previewing,
  error,
}: {
  preview: PreviewResponse | null;
  previewing: boolean;
  error: string | null;
}) {
  if (previewing) return <p className="text-xs text-slate-400">Running preview on recent candles…</p>;
  if (error)
    return (
      <p className="rounded bg-red-50 px-2 py-1 text-[11px] text-red-700 ring-1 ring-inset ring-red-100">
        {error}
      </p>
    );
  if (!preview) return null;

  const fmt = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(2);

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span className="font-semibold text-slate-700">
          {preview.symbol} · {preview.timeframe}
        </span>
        <span className="text-slate-500">{preview.bars_evaluated} bars</span>
        <span className="text-slate-500">provider: {preview.provider}</span>
        {preview.is_demo && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
            DEMO DATA
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-md bg-white p-2 ring-1 ring-inset ring-slate-100">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Entry signals</p>
          <p className="text-base font-semibold text-emerald-600">{preview.entry_signals}</p>
        </div>
        <div className="rounded-md bg-white p-2 ring-1 ring-inset ring-slate-100">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Exit signals</p>
          <p className="text-base font-semibold text-red-500">{preview.exit_signals}</p>
        </div>
        <div className="rounded-md bg-white p-2 ring-1 ring-inset ring-slate-100">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Last bar entry</p>
          <p className={`text-sm font-semibold ${preview.last_bar_entry_signal ? "text-emerald-600" : "text-slate-400"}`}>
            {preview.last_bar_entry_signal ? "YES" : "no"}
          </p>
        </div>
        <div className="rounded-md bg-white p-2 ring-1 ring-inset ring-slate-100">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Last bar exit</p>
          <p className={`text-sm font-semibold ${preview.last_bar_exit_signal ? "text-red-500" : "text-slate-400"}`}>
            {preview.last_bar_exit_signal ? "YES" : "no"}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        {Object.entries(preview.indicator_tail).map(([id, outputs]) => (
          <span key={id} className="rounded bg-white px-2 py-1 text-[11px] text-slate-600 ring-1 ring-inset ring-slate-100">
            <span className="font-mono font-semibold text-indigo-600">{id}</span>{" "}
            {Object.entries(outputs)
              .map(([out, val]) => `${out}=${fmt(val)}`)
              .join(" ")}
          </span>
        ))}
      </div>
    </div>
  );
}
