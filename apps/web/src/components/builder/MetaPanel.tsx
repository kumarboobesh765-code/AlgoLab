"use client";

import type { StrategyMeta } from "@/lib/builder-workflow";

const inputCls =
  "w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100";

export default function MetaPanel({
  meta,
  onChange,
}: {
  meta: StrategyMeta;
  onChange: (next: StrategyMeta) => void;
}) {
  const set = (patch: Partial<StrategyMeta>) => onChange({ ...meta, ...patch });

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-xs font-medium text-slate-600">
        Strategy name *
        <input
          value={meta.name}
          onChange={(e) => set({ name: e.target.value })}
          placeholder="e.g. NIFTY EMA Pullback"
          className={`${inputCls} mt-1`}
        />
      </label>
      <label className="text-xs font-medium text-slate-600">
        Type
        <select
          value={meta.strategy_type}
          onChange={(e) => set({ strategy_type: e.target.value })}
          className={`${inputCls} mt-1`}
        >
          <option value="intraday">Intraday</option>
          <option value="btst">BTST</option>
          <option value="positional">Positional</option>
        </select>
      </label>
      <label className="text-xs font-medium text-slate-600 sm:col-span-2">
        Description
        <input
          value={meta.description}
          onChange={(e) => set({ description: e.target.value })}
          placeholder="What does this strategy do?"
          className={`${inputCls} mt-1`}
        />
      </label>
      <label className="text-xs font-medium text-slate-600 sm:col-span-2">
        Tags (comma-separated)
        <input
          value={meta.tags}
          onChange={(e) => set({ tags: e.target.value })}
          placeholder="ema, pullback, nifty"
          className={`${inputCls} mt-1`}
        />
      </label>
    </div>
  );
}
