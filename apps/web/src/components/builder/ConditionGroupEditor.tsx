"use client";

import type { Condition, ConditionGroup } from "@/lib/builders";
import { defaultCondition, isCondition } from "@/lib/builders";
import ConditionRow, { AddConditionButton, conditionSummary } from "@/components/builder/ConditionRow";

interface EditorContext {
  indicatorIds: string[];
  indicatorOutputs: Record<string, string[]>;
  variableNames: string[];
}

export default function ConditionGroupEditor({
  group,
  title,
  tone = "green",
  context,
  onChange,
  depth = 0,
}: {
  group: ConditionGroup;
  title: string;
  tone?: "green" | "red";
  context: EditorContext;
  onChange: (next: ConditionGroup) => void;
  depth?: number;
}) {
  const accent =
    tone === "green"
      ? "border-emerald-200 bg-emerald-50/40"
      : "border-red-200 bg-red-50/40";
  const badge =
    tone === "green" ? "bg-emerald-600" : "bg-red-500";

  const updateChild = (index: number, next: Condition | ConditionGroup) => {
    const conditions = group.conditions.map((c, i) => (i === index ? next : c));
    onChange({ ...group, conditions });
  };

  const removeChild = (index: number) => {
    onChange({ ...group, conditions: group.conditions.filter((_, i) => i !== index) });
  };

  return (
    <div className={`rounded-xl border ${accent} p-3`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white ${badge}`}>
          {title}
        </span>
        <div className="flex overflow-hidden rounded-md border border-slate-200 bg-white text-[11px]">
          {(["ALL", "ANY"] as const).map((logic) => (
            <button
              key={logic}
              onClick={() => onChange({ ...group, logic })}
              className={`px-2 py-1 font-medium ${
                group.logic === logic ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-50"
              }`}
            >
              {logic === "ALL" ? "Match ALL" : "Match ANY"}
            </button>
          ))}
        </div>
        <span className="text-[10px] text-slate-400">
          {group.conditions.length} condition{group.conditions.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="space-y-1.5">
        {group.conditions.length === 0 && (
          <p className="py-2 text-center text-xs text-slate-400">
            No conditions yet — add one below.
          </p>
        )}
        {group.conditions.map((child, i) =>
          isCondition(child) ? (
            <div key={i}>
              {i > 0 && (
                <p className="my-0.5 text-center text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  {group.logic === "ALL" ? "and" : "or"}
                </p>
              )}
              <ConditionRow
                condition={child}
                indicatorIds={context.indicatorIds}
                indicatorOutputs={context.indicatorOutputs}
                variableNames={context.variableNames}
                onChange={(next) => updateChild(i, next)}
                onRemove={() => removeChild(i)}
              />
            </div>
          ) : (
            <div key={i} className="pl-3">
              {i > 0 && (
                <p className="my-0.5 text-center text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  {group.logic === "ALL" ? "and" : "or"}
                </p>
              )}
              <ConditionGroupEditor
                group={child}
                title="Sub-group"
                tone={tone}
                context={context}
                onChange={(next) => updateChild(i, next)}
                depth={depth + 1}
              />
            </div>
          ),
        )}
      </div>

      <div className="mt-2 flex gap-2">
        <AddConditionButton
          onClick={() =>
            onChange({ ...group, conditions: [...group.conditions, defaultCondition()] })
          }
        />
        {depth < 2 && (
          <button
            onClick={() =>
              onChange({
                ...group,
                conditions: [
                  ...group.conditions,
                  { logic: "ANY", conditions: [defaultCondition()] },
                ],
              })
            }
            className="rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs text-slate-500 hover:border-blue-400 hover:text-blue-600"
          >
            + Add sub-group
          </button>
        )}
      </div>
    </div>
  );
}

/** Flat readable summary used by flow view + library cards. */
export function summarizeGroup(group: ConditionGroup): string[] {
  return group.conditions.map((c) => (isCondition(c) ? conditionSummary(c) : "(sub-group)"));
}
