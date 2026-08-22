"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui/Card";
import MetaPanel from "@/components/builder/MetaPanel";
import IndicatorsEditor from "@/components/builder/IndicatorsEditor";
import ConditionGroupEditor from "@/components/builder/ConditionGroupEditor";
import {
  PreviewPanel,
  ValidationPanel,
} from "@/components/builder/ValidationPanel";
import {
  EMPTY_META,
  useBuilderWorkflow,
  type StrategyMeta,
} from "@/lib/builder-workflow";
import {
  emptyDefinition,
  quickIssues,
  TIMEFRAMES,
  type StrategyDefinitionV1,
} from "@/lib/builders";

const inputCls =
  "rounded-md border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100";

export default function VisualBuilderPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const workflow = useBuilderWorkflow();
  const [meta, setMeta] = useState<StrategyMeta>(EMPTY_META);
  const [definition, setDefinition] = useState<StrategyDefinitionV1>(emptyDefinition());

  const indicatorIds = useMemo(() => definition.indicators.map((i) => i.id), [definition]);
  const indicatorOutputs = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const ind of definition.indicators) {
      const entry = workflow.catalog?.indicators.find((c) => c.type === ind.type);
      map[ind.id] = entry?.outputs ?? [];
    }
    return map;
  }, [definition.indicators, workflow.catalog]);

  const context = {
    indicatorIds,
    indicatorOutputs,
    variableNames: definition.variables.map((v) => v.name),
  };

  const localIssues = quickIssues(definition);
  const canSave = meta.name.trim().length > 0 && localIssues.length === 0;

  if (!authLoading && !user) {
    return (
      <Card>
        <div className="py-10 text-center">
          <p className="text-sm text-slate-500">Sign in to build strategies.</p>
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

  async function handleSave() {
    try {
      const created = await workflow.save(meta, definition);
      router.push(`/strategies?created=${encodeURIComponent(created.name)}`);
    } catch {
      /* saveError rendered by workflow state */
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-slate-800">Visual Builder</h1>
          <p className="text-xs text-slate-400">
            Compose the canonical strategy definition — every builder compiles to the same JSON.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => workflow.validate(definition)}
            disabled={workflow.validating}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {workflow.validating ? "Validating…" : "Validate"}
          </button>
          <button
            onClick={() => workflow.runPreview(definition)}
            disabled={workflow.previewing || localIssues.length > 0}
            title={localIssues.length > 0 ? localIssues[0] : undefined}
            className="rounded-lg border border-blue-300 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          >
            {workflow.previewing ? "Previewing…" : "Preview signals"}
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave || workflow.saving}
            title={localIssues.length > 0 ? localIssues[0] : undefined}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {workflow.saving ? "Saving…" : "Save strategy"}
          </button>
        </div>
      </div>

      {(workflow.saveError || localIssues.length > 0) && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {workflow.saveError ?? localIssues.join(" · ")}
        </p>
      )}

      <Card title="1 · Strategy details">
        <MetaPanel meta={meta} onChange={setMeta} />
      </Card>

      <Card title="2 · Instrument & timeframe">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs font-medium text-slate-600">
            Symbol
            <input
              value={definition.instrument.symbol}
              onChange={(e) =>
                setDefinition({
                  ...definition,
                  instrument: {
                    ...definition.instrument,
                    symbol: e.target.value.toUpperCase(),
                  },
                })
              }
              className={`${inputCls} mt-1 block w-32 uppercase`}
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Exchange
            <select
              value={definition.instrument.exchange}
              onChange={(e) =>
                setDefinition({
                  ...definition,
                  instrument: { ...definition.instrument, exchange: e.target.value },
                })
              }
              className={`${inputCls} mt-1 block w-24`}
            >
              <option>NSE</option>
              <option>BSE</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Segment
            <select
              value={definition.instrument.segment}
              onChange={(e) =>
                setDefinition({
                  ...definition,
                  instrument: { ...definition.instrument, segment: e.target.value },
                })
              }
              className={`${inputCls} mt-1 block w-28`}
            >
              <option value="index">Index</option>
              <option value="equity">Equity</option>
              <option value="futures">Futures</option>
              <option value="options">Options</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Timeframe
            <select
              value={definition.timeframe}
              onChange={(e) => setDefinition({ ...definition, timeframe: e.target.value })}
              className={`${inputCls} mt-1 block w-24`}
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf}>{tf}</option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      <Card title="3 · Indicators" subtitle="Reference them in conditions by id">
        <IndicatorsEditor
          definition={definition.indicators}
          catalog={workflow.catalog}
          onChange={(indicators) => setDefinition({ ...definition, indicators })}
        />
      </Card>

      <Card title="4 · Variables (optional)" subtitle="Named numbers reusable across params and conditions">
        {definition.variables.length === 0 ? (
          <button
            onClick={() =>
              setDefinition({
                ...definition,
                variables: [{ name: "threshold", value: 100 }],
              })
            }
            className="rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs text-slate-500 hover:border-blue-400 hover:text-blue-600"
          >
            + Add variable
          </button>
        ) : (
          <div className="space-y-1.5">
            {definition.variables.map((v, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={v.name}
                  onChange={(e) => {
                    const name = e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_");
                    const variables = definition.variables.map((x, j) =>
                      j === i ? { ...x, name } : x,
                    );
                    setDefinition({ ...definition, variables });
                  }}
                  placeholder="name"
                  className="w-40 rounded-md border border-slate-200 px-2 py-1.5 font-mono text-xs outline-none focus:border-blue-500"
                />
                <span className="text-xs text-slate-400">=</span>
                <input
                  type="number"
                  step="any"
                  value={v.value}
                  onChange={(e) => {
                    const variables = definition.variables.map((x, j) =>
                      j === i ? { ...x, value: Number(e.target.value) } : x,
                    );
                    setDefinition({ ...definition, variables });
                  }}
                  className="w-28 rounded-md border border-slate-200 px-2 py-1.5 text-xs tabular-nums outline-none focus:border-blue-500"
                />
                <button
                  onClick={() =>
                    setDefinition({
                      ...definition,
                      variables: definition.variables.filter((_, j) => j !== i),
                    })
                  }
                  className="rounded px-1.5 py-0.5 text-xs text-slate-300 hover:bg-red-50 hover:text-red-500"
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              onClick={() =>
                setDefinition({
                  ...definition,
                  variables: [
                    ...definition.variables,
                    { name: `var_${definition.variables.length + 1}`, value: 0 },
                  ],
                })
              }
              className="mt-1 rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs text-slate-500 hover:border-blue-400 hover:text-blue-600"
            >
              + Add variable
            </button>
          </div>
        )}
      </Card>

      <Card title="5 · Entry rules" subtitle="When all/any of these are true, enter a position">
        <ConditionGroupEditor
          group={definition.entry}
          title="Entry"
          tone="green"
          context={context}
          onChange={(entry) => setDefinition({ ...definition, entry })}
        />
      </Card>

      <Card
        title="6 · Exit rules (optional)"
        subtitle={
          definition.exit
            ? undefined
            : "Without exit rules, positions close only via risk targets"
        }
        actions={
          definition.exit ? (
            <button
              onClick={() => setDefinition({ ...definition, exit: null })}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
            >
              Remove exit rules
            </button>
          ) : (
            <button
              onClick={() =>
                setDefinition({
                  ...definition,
                  exit: { logic: "ANY", conditions: [] },
                })
              }
              className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
            >
              + Define exit rules
            </button>
          )
        }
      >
        {definition.exit ? (
          <ConditionGroupEditor
            group={definition.exit}
            title="Exit"
            tone="red"
            context={context}
            onChange={(exit) => setDefinition({ ...definition, exit })}
          />
        ) : (
          <p className="py-2 text-center text-xs text-slate-400">No exit rules defined.</p>
        )}
      </Card>

      <Card title="7 · Risk & position">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(
            [
              ["stop_loss_pct", "Stop loss %"],
              ["target_pct", "Target %"],
              ["trailing_sl_pct", "Trailing SL %"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="text-xs font-medium text-slate-600">
              {label}
              <input
                type="number"
                step="any"
                min="0"
                value={definition.risk?.[key] ?? ""}
                onChange={(e) => {
                  const raw = e.target.value === "" ? null : Number(e.target.value);
                  const risk = {
                    stop_loss_pct: null,
                    target_pct: null,
                    trailing_sl_pct: null,
                    ...definition.risk,
                    [key]: raw,
                  };
                  setDefinition({ ...definition, risk });
                }}
                placeholder="—"
                className={`${inputCls} mt-1 block w-full tabular-nums`}
              />
            </label>
          ))}
          <label className="text-xs font-medium text-slate-600">
            Direction
            <select
              value={definition.position.direction}
              onChange={(e) =>
                setDefinition({
                  ...definition,
                  position: {
                    ...definition.position,
                    direction: e.target.value as typeof definition.position.direction,
                  },
                })
              }
              className={`${inputCls} mt-1 block w-full`}
            >
              <option value="long_only">Long only</option>
              <option value="short_only">Short only</option>
              <option value="both">Long & short</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Quantity type
            <select
              value={definition.position.quantity_type}
              onChange={(e) =>
                setDefinition({
                  ...definition,
                  position: {
                    ...definition.position,
                    quantity_type: e.target.value as typeof definition.position.quantity_type,
                  },
                })
              }
              className={`${inputCls} mt-1 block w-full`}
            >
              <option value="fixed">Fixed</option>
              <option value="capital_pct">% of capital</option>
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            {definition.position.quantity_type === "fixed" ? "Quantity" : "% of capital"}
            <input
              type="number"
              step="any"
              min="0"
              value={
                definition.position.quantity_type === "fixed"
                  ? definition.position.quantity
                  : (definition.position.capital_pct ?? "")
              }
              onChange={(e) => {
                const num = Number(e.target.value);
                setDefinition({
                  ...definition,
                  position:
                    definition.position.quantity_type === "fixed"
                      ? { ...definition.position, quantity: num }
                      : { ...definition.position, capital_pct: num },
                });
              }}
              className={`${inputCls} mt-1 block w-full tabular-nums`}
            />
          </label>
        </div>
      </Card>

      <Card title="Validation & preview">
        <div className="space-y-3">
          <ValidationPanel validation={workflow.validation} validating={workflow.validating} />
          <PreviewPanel
            preview={workflow.preview}
            previewing={workflow.previewing}
            error={workflow.previewError}
          />
        </div>
      </Card>
    </div>
  );
}
