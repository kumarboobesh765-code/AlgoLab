"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui/Card";
import MetaPanel from "@/components/builder/MetaPanel";
import IndicatorsEditor from "@/components/builder/IndicatorsEditor";
import ConditionGroupEditor, {
  summarizeGroup,
} from "@/components/builder/ConditionGroupEditor";
import { PreviewPanel, ValidationPanel } from "@/components/builder/ValidationPanel";
import { EMPTY_META, useBuilderWorkflow, type StrategyMeta } from "@/lib/builder-workflow";
import { emptyDefinition, quickIssues, TIMEFRAMES, type StrategyDefinitionV1 } from "@/lib/builders";
import { useAppSettings } from "@/lib/settings";

function FlowNode({
  step,
  title,
  subtitle,
  tone,
  children,
}: {
  step: string;
  title: string;
  subtitle?: string;
  tone: "slate" | "green" | "red" | "blue";
  children: React.ReactNode;
}) {
  const tones = {
    slate: "border-slate-300",
    green: "border-emerald-400",
    red: "border-red-400",
    blue: "border-blue-400",
  };
  return (
    <div className={`rounded-xl border-2 ${tones[tone]} bg-white p-4 shadow-sm`}>
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-800 text-[11px] font-bold text-white">
          {step}
        </span>
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {subtitle && <span className="text-[11px] text-slate-400">{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}

function FlowConnector({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center py-0.5">
      <span className="h-4 w-px bg-slate-300" />
      <span className="-my-2 h-2 w-2 rotate-45 border-b border-r border-slate-300" />
      {label && (
        <span className="my-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </span>
      )}
    </div>
  );
}

export default function StrategyFlowPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const workflow = useBuilderWorkflow();
  const savedTimeframe = useAppSettings().timeframe;
  const [meta, setMeta] = useState<StrategyMeta>(EMPTY_META);
  const [definition, setDefinition] = useState<StrategyDefinitionV1>(() =>
    emptyDefinition(savedTimeframe),
  );
  const [editing, setEditing] = useState(false);

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
  const entryLines = summarizeGroup(definition.entry);
  const exitLines = definition.exit ? summarizeGroup(definition.exit) : [];

  if (!authLoading && !user) {
    return (
      <Card>
        <div className="py-10 text-center">
          <p className="text-sm text-slate-500">Connecting to the API…</p>
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
          <h1 className="text-lg font-semibold text-slate-800">Strategy Flow</h1>
          <p className="text-xs text-slate-400">
            The strategy as a pipeline — data in, signals out. Click &quot;Edit flow&quot; to modify.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setEditing(!editing)}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {editing ? "View flow" : "Edit flow"}
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
            onClick={() => workflow.validate(definition)}
            disabled={workflow.validating || localIssues.length > 0}
            title={localIssues.length > 0 ? localIssues[0] : undefined}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {workflow.validating ? "Validating…" : "Validate"}
          </button>
          <button
            onClick={handleSave}
            disabled={!meta.name.trim() || localIssues.length > 0 || workflow.saving}
            title={localIssues.length > 0 ? localIssues[0] : !meta.name.trim() ? "Enter a strategy name" : undefined}
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

      {workflow.validation && (
        <Card title="Validation">
          <ValidationPanel validation={workflow.validation} validating={workflow.validating} />
        </Card>
      )}

      {editing ? (
        <div className="space-y-4">
          <Card title="Strategy details">
            <MetaPanel meta={meta} onChange={setMeta} />
          </Card>
          <Card title="Instrument & timeframe">
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-xs font-medium text-slate-600">
                Symbol
                <input
                  value={definition.instrument.symbol}
                  onChange={(e) =>
                    setDefinition({
                      ...definition,
                      instrument: { ...definition.instrument, symbol: e.target.value.toUpperCase() },
                    })
                  }
                  className="mt-1 block w-32 rounded-md border border-slate-200 px-3 py-2 text-sm uppercase outline-none focus:border-blue-500"
                />
              </label>
              <label className="text-xs font-medium text-slate-600">
                Timeframe
                <select
                  value={definition.timeframe}
                  onChange={(e) => setDefinition({ ...definition, timeframe: e.target.value })}
                  className="mt-1 block w-24 rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500"
                >
                  {TIMEFRAMES.map((tf) => (
                    <option key={tf}>{tf}</option>
                  ))}
                </select>
              </label>
            </div>
          </Card>
          <Card title="Indicators">
            <IndicatorsEditor
              definition={definition.indicators}
              catalog={workflow.catalog}
              catalogError={workflow.catalogError}
              onChange={(indicators) => setDefinition({ ...definition, indicators })}
            />
          </Card>
          <Card title="Entry rules">
            <ConditionGroupEditor
              group={definition.entry}
              title="Entry"
              tone="green"
              context={context}
              onChange={(entry) => setDefinition({ ...definition, entry })}
            />
          </Card>
          <Card
            title="Exit rules (optional)"
            actions={
              definition.exit ? (
                <button
                  onClick={() => setDefinition({ ...definition, exit: null })}
                  className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
                >
                  Remove
                </button>
              ) : (
                <button
                  onClick={() =>
                    setDefinition({ ...definition, exit: { logic: "ANY", conditions: [] } })
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
        </div>
      ) : (
        <div className="mx-auto max-w-2xl">
          <FlowNode step="1" title={`${definition.instrument.symbol} · ${definition.timeframe}`} subtitle="market data" tone="slate">
            <p className="text-xs text-slate-500">
              Candles stream from the active provider ({workflow.preview?.provider ?? "demo"}).
            </p>
          </FlowNode>
          <FlowConnector label="compute" />
          <FlowNode step="2" title="Indicators" subtitle={`${definition.indicators.length} defined`} tone="blue">
            {definition.indicators.length === 0 ? (
              <p className="text-xs text-slate-400">None — conditions use raw price fields.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {definition.indicators.map((ind) => (
                  <span key={ind.id} className="rounded bg-indigo-50 px-2 py-1 font-mono text-[11px] text-indigo-700 ring-1 ring-inset ring-indigo-100">
                    {ind.id} = {ind.type}
                  </span>
                ))}
              </div>
            )}
          </FlowNode>
          <FlowConnector label="evaluate" />
          <FlowNode
            step="3"
            title="Entry signal"
            subtitle={`match ${definition.entry.logic}`}
            tone="green"
          >
            {entryLines.length === 0 ? (
              <p className="text-xs text-slate-400">No conditions yet.</p>
            ) : (
              <ul className="space-y-1">
                {entryLines.map((line, i) => (
                  <li key={i} className="rounded bg-emerald-50 px-2 py-1 font-mono text-[11px] text-emerald-800">
                    {i > 0 && definition.entry.logic === "ALL" ? "AND " : ""}
                    {line}
                  </li>
                ))}
              </ul>
            )}
          </FlowNode>
          <FlowConnector label={definition.exit ? "on open position" : "hold"} />
          {definition.exit ? (
            <FlowNode step="4" title="Exit signal" subtitle={`match ${definition.exit.logic}`} tone="red">
              <ul className="space-y-1">
                {exitLines.map((line, i) => (
                  <li key={i} className="rounded bg-red-50 px-2 py-1 font-mono text-[11px] text-red-700">
                    {i > 0 && definition.exit!.logic === "ALL" ? "AND " : ""}
                    {line}
                  </li>
                ))}
              </ul>
            </FlowNode>
          ) : (
            <FlowNode step="4" title="Risk exits only" tone="slate">
              <p className="text-xs text-slate-500">
                Stop loss / target close positions; no rule-based exits.
              </p>
            </FlowNode>
          )}
          <FlowConnector label="execute" />
          <FlowNode step="5" title="Paper execution" subtitle="Phase 7" tone="slate">
            <p className="text-xs text-slate-400">
              Virtual orders only — the paper engine consumes this same definition.
            </p>
          </FlowNode>
        </div>
      )}

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
