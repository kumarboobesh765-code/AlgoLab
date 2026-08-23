"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui/Card";
import MetaPanel from "@/components/builder/MetaPanel";
import { PreviewPanel, ValidationPanel } from "@/components/builder/ValidationPanel";
import { EMPTY_META, useBuilderWorkflow, type StrategyMeta } from "@/lib/builder-workflow";
import {
  emptyDefinition,
  STRATEGY_EDIT_KEY,
  TEMPLATE_HANDOFF_KEY,
  TEMPLATE_HANDOFF_NAME,
  type StrategyDefinitionV1,
} from "@/lib/builders";
import { useAppSettings } from "@/lib/settings";

export { TEMPLATE_HANDOFF_KEY, TEMPLATE_HANDOFF_NAME };

function templateJson(timeframe: string): string {
  return JSON.stringify(
    {
      version: 1,
      timeframe,
      instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
      variables: [{ name: "fast_len", value: 9 }],
      indicators: [
        { id: "ema_fast", type: "EMA", params: { length: { var: "fast_len" } } },
        { id: "ema_slow", type: "EMA", params: { length: 21 } },
        { id: "rsi", type: "RSI", params: { length: 14 } },
      ],
      entry: {
        logic: "ALL",
        conditions: [
          {
            left: { kind: "indicator", ref: "ema_fast" },
            op: "CROSS_ABOVE",
            right: { kind: "indicator", ref: "ema_slow" },
          },
          {
            left: { kind: "indicator", ref: "rsi.rsi" },
            op: "GT",
            right: { kind: "constant", value: 50 },
          },
        ],
      },
      exit: {
        logic: "ANY",
        conditions: [
          {
            left: { kind: "indicator", ref: "ema_fast" },
            op: "CROSS_BELOW",
            right: { kind: "indicator", ref: "ema_slow" },
          },
        ],
      },
      risk: { stop_loss_pct: 1.0, target_pct: 2.0, trailing_sl_pct: null },
      position: {
        direction: "long_only",
        quantity_type: "fixed",
        quantity: 1,
        capital_pct: null,
      },
    },
    null,
    2,
  );
}

export default function TechnicalBuilderPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const workflow = useBuilderWorkflow();
  const savedTimeframe = useAppSettings().timeframe;
  const [meta, setMeta] = useState<StrategyMeta>(EMPTY_META);
  const [text, setText] = useState(() => templateJson(savedTimeframe));
  const [parseError, setParseError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Handoff from Strategy Library ("View JSON" / "Edit") — read via microtask
  // so the effect body itself never calls setState (react-compiler rule).
  useEffect(() => {
    let raw: string | null = null;
    let name: string | null = null;
    let editId: string | null = null;
    try {
      raw = sessionStorage.getItem(TEMPLATE_HANDOFF_KEY);
      name = sessionStorage.getItem(TEMPLATE_HANDOFF_NAME);
      editId = sessionStorage.getItem(STRATEGY_EDIT_KEY);
      if (raw !== null) sessionStorage.removeItem(TEMPLATE_HANDOFF_KEY);
      if (name !== null) sessionStorage.removeItem(TEMPLATE_HANDOFF_NAME);
      if (editId !== null) sessionStorage.removeItem(STRATEGY_EDIT_KEY);
    } catch {
      return;
    }
    if (raw === null && editId === null) return;
    Promise.resolve().then(() => {
      if (raw !== null) setText(raw);
      if (name) setMeta((m) => ({ ...m, name }));
      if (editId !== null) setEditingId(editId);
    });
  }, []);

  if (!authLoading && !user) {
    return (
      <Card>
        <div className="py-10 text-center">
          <p className="text-sm text-slate-500">Connecting to the API…</p>
        </div>
      </Card>
    );
  }

  function parseDefinition(): StrategyDefinitionV1 | null {
    setParseError(null);
    try {
      return JSON.parse(text) as StrategyDefinitionV1;
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Invalid JSON");
      return null;
    }
  }

  async function handleValidate() {
    const def = parseDefinition();
    if (def) await workflow.validate(def);
  }

  async function handlePreview() {
    const def = parseDefinition();
    if (def) await workflow.runPreview(def);
  }

  async function handleSave() {
    const def = parseDefinition();
    if (!def) return;
    try {
      const created = await workflow.save(meta, def, editingId ?? undefined);
      router.push(`/strategies?created=${encodeURIComponent(created.name)}`);
    } catch {
      /* saveError rendered below */
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-slate-800">Technical Builder</h1>
          <p className="text-xs text-slate-400">
            {editingId
              ? "Editing an existing strategy — saving updates it (a new version is created)."
              : "Edit the canonical definition JSON directly — full power, no guardrails."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setText(JSON.stringify(emptyDefinition(savedTimeframe), null, 2))}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Empty template
          </button>
          <button
            onClick={() => setText(templateJson(savedTimeframe))}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            EMA cross example
          </button>
          <button
            onClick={handleValidate}
            disabled={workflow.validating}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {workflow.validating ? "Validating…" : "Validate"}
          </button>
          <button
            onClick={handlePreview}
            disabled={workflow.previewing || parseError !== null}
            className="rounded-lg border border-blue-300 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          >
            {workflow.previewing ? "Previewing…" : "Preview signals"}
          </button>
          <button
            onClick={handleSave}
            disabled={!meta.name.trim() || workflow.saving || parseError !== null}
            title={!meta.name.trim() ? "Enter a strategy name" : undefined}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {workflow.saving ? "Saving…" : "Save strategy"}
          </button>
        </div>
      </div>

      {(workflow.saveError || parseError) && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {workflow.saveError ?? `JSON error: ${parseError}`}
        </p>
      )}

      <Card title="Strategy details">
        <MetaPanel meta={meta} onChange={setMeta} />
      </Card>

      <Card title="Definition JSON">
        <div className="mb-2 flex justify-end">
          <a
            href="/docs/strategy-definition.md"
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-sky-600 hover:text-sky-700"
          >
            Schema v1 reference ↗
          </a>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          rows={24}
          className="w-full rounded-lg border border-slate-200 bg-slate-900 p-4 font-mono text-[12px] leading-relaxed text-slate-100 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
        />
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
