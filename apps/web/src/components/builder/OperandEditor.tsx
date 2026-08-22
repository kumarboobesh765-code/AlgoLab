"use client";

import type { Operand } from "@/lib/builders";
import { PRICE_SOURCES } from "@/lib/builders";

const KINDS: { value: Operand["kind"]; label: string }[] = [
  { value: "price", label: "Price" },
  { value: "indicator", label: "Indicator" },
  { value: "constant", label: "Value" },
  { value: "variable", label: "Variable" },
  { value: "formula", label: "Formula" },
];

const inputCls =
  "rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-blue-500";

export default function OperandEditor({
  operand,
  indicatorIds,
  indicatorOutputs,
  variableNames,
  onChange,
}: {
  operand: Operand;
  indicatorIds: string[];
  indicatorOutputs: Record<string, string[]>;
  variableNames: string[];
  onChange: (next: Operand) => void;
}) {
  const set = (patch: Partial<Operand>) => onChange({ ...operand, ...patch });

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <select
        value={operand.kind}
        onChange={(e) => {
          const kind = e.target.value as Operand["kind"];
          const next: Operand = { kind };
          if (kind === "price") next.price = "close";
          if (kind === "constant") next.value = 0;
          if (kind === "indicator") {
            const first = indicatorIds[0];
            if (first) {
              const outs = indicatorOutputs[first];
              next.ref = outs && outs.length > 1 ? `${first}.${outs[0]}` : first;
            }
          }
          if (kind === "variable") next.name = variableNames[0] ?? "";
          if (kind === "formula") next.expression = "";
          onChange(next);
        }}
        className={`${inputCls} w-24`}
      >
        {KINDS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </select>

      {operand.kind === "price" && (
        <select
          value={operand.price ?? "close"}
          onChange={(e) => set({ price: e.target.value })}
          className={inputCls}
        >
          {PRICE_SOURCES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      )}

      {operand.kind === "indicator" && (
        <select
          value={operand.ref ?? ""}
          onChange={(e) => set({ ref: e.target.value })}
          className={`${inputCls} max-w-44`}
        >
          {!operand.ref && <option value="">Select…</option>}
          {indicatorIds.flatMap((id) => {
            const outs = indicatorOutputs[id];
            if (!outs || outs.length <= 1) {
              return [<option key={id} value={id}>{id}</option>];
            }
            return outs.map((o) => (
              <option key={`${id}.${o}`} value={`${id}.${o}`}>
                {id}.{o}
              </option>
            ));
          })}
        </select>
      )}

      {operand.kind === "constant" && (
        <input
          type="number"
          step="any"
          value={operand.value ?? 0}
          onChange={(e) => set({ value: Number(e.target.value) })}
          className={`${inputCls} w-24`}
        />
      )}

      {operand.kind === "variable" && (
        <select
          value={operand.name ?? ""}
          onChange={(e) => set({ name: e.target.value })}
          className={inputCls}
        >
          {variableNames.length === 0 && <option value="">No variables</option>}
          {variableNames.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      )}

      {operand.kind === "formula" && (
        <input
          type="text"
          placeholder="close - ema_fast"
          value={operand.expression ?? ""}
          onChange={(e) => set({ expression: e.target.value })}
          className={`${inputCls} w-56 font-mono`}
        />
      )}
    </div>
  );
}
