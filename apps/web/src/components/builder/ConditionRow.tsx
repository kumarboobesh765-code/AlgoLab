"use client";

import type { Condition } from "@/lib/builders";
import { defaultCondition, operandLabel, operatorLabel, OPERATORS } from "@/lib/builders";
import OperandEditor from "@/components/builder/OperandEditor";

export default function ConditionRow({
  condition,
  indicatorIds,
  indicatorOutputs,
  variableNames,
  onChange,
  onRemove,
}: {
  condition: Condition;
  indicatorIds: string[];
  indicatorOutputs: Record<string, string[]>;
  variableNames: string[];
  onChange: (next: Condition) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-100 bg-white px-3 py-2">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-300">IF</span>
      <OperandEditor
        operand={condition.left}
        indicatorIds={indicatorIds}
        indicatorOutputs={indicatorOutputs}
        variableNames={variableNames}
        onChange={(left) => onChange({ ...condition, left })}
      />
      <select
        value={condition.op}
        onChange={(e) => onChange({ ...condition, op: e.target.value })}
        title={operatorLabel(condition.op)}
        className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1.5 text-xs font-medium text-blue-700 outline-none focus:border-blue-500"
      >
        {OPERATORS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <OperandEditor
        operand={condition.right}
        indicatorIds={indicatorIds}
        indicatorOutputs={indicatorOutputs}
        variableNames={variableNames}
        onChange={(right) => onChange({ ...condition, right })}
      />
      <button
        onClick={onRemove}
        title="Remove condition"
        className="ml-auto rounded px-1.5 py-0.5 text-xs text-slate-300 hover:bg-red-50 hover:text-red-500"
      >
        ✕
      </button>
    </div>
  );
}

export function AddConditionButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={() => onClick()}
      className="rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs text-slate-500 hover:border-blue-400 hover:text-blue-600"
    >
      + Add condition
    </button>
  );
}

export function conditionSummary(c: Condition): string {
  return `${operandLabel(c.left)} ${operatorLabel(c.op)} ${operandLabel(c.right)}`;
}

export function makeCondition(): Condition {
  return defaultCondition();
}
