"use client";

import type { IndicatorCatalogEntry, QuantCatalog } from "@/lib/api";
import type { IndicatorDef } from "@/lib/builders";
import { catalogEntry, uniqueIndicatorId } from "@/lib/builders";

const inputCls =
  "rounded-md border border-slate-200 bg-white px-2 py-1 text-xs outline-none focus:border-blue-500";

export default function IndicatorsEditor({
  definition,
  catalog,
  catalogError,
  onChange,
}: {
  definition: IndicatorDef[];
  catalog: QuantCatalog | null;
  catalogError?: string | null;
  onChange: (next: IndicatorDef[]) => void;
}) {
  const add = (entry: IndicatorCatalogEntry) => {
    const id = uniqueIndicatorId(entry.type, definition.map((i) => i.id));
    const params: IndicatorDef["params"] = {};
    for (const [name, spec] of Object.entries(entry.params)) params[name] = spec.default;
    onChange([...definition, { id, type: entry.type, params }]);
  };

  const update = (index: number, patch: Partial<IndicatorDef>) => {
    onChange(definition.map((ind, i) => (i === index ? { ...ind, ...patch } : ind)));
  };

  const setParam = (index: number, name: string, raw: string) => {
    const ind = definition[index];
    const entry = catalogEntry(catalog, ind.type);
    const spec = entry?.params[name];
    let value: number | string | { var: string };
    if (raw.startsWith("$")) {
      value = { var: raw.slice(1) };
    } else if (spec?.kind === "int") {
      value = Math.round(Number(raw));
    } else if (spec?.kind === "float") {
      value = Number(raw);
    } else {
      value = raw;
    }
    update(index, { params: { ...ind.params, [name]: value } });
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value=""
          onChange={(e) => {
            const entry = catalogEntry(catalog, e.target.value);
            if (entry) add(entry);
            e.target.value = "";
          }}
          className={`${inputCls} max-w-56`}
          disabled={!catalog}
        >
          <option value="">
            {catalog ? "+ Add indicator…" : catalogError ? "Catalog unavailable" : "Loading catalog…"}
          </option>
          {catalog?.indicators.map((entry) => (
            <option key={entry.type} value={entry.type}>
              {entry.type} — {entry.description}
            </option>
          ))}
        </select>
        {catalogError && (
          <span className="text-[11px] text-red-500">{catalogError}</span>
        )}
      </div>

      {definition.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-200 py-4 text-center text-xs text-slate-400">
          No indicators yet. Conditions can still use price fields and formulas.
        </p>
      ) : (
        <div className="space-y-1.5">
          {definition.map((ind, idx) => {
            const entry = catalogEntry(catalog, ind.type);
            return (
              <div
                key={idx}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-100 bg-white px-3 py-2"
              >
                <input
                  value={ind.id}
                  onChange={(e) =>
                    update(idx, {
                      id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
                    })
                  }
                  title="Reference id used in conditions"
                  className="w-28 rounded bg-indigo-50 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-indigo-700 outline-none focus:ring-2 focus:ring-indigo-200"
                />
                <span className="text-[11px] text-slate-400">{entry?.description}</span>
                <div className="ml-auto flex flex-wrap items-center gap-1.5">
                  {Object.entries(ind.params).map(([name, value]) => (
                    <label key={name} className="flex items-center gap-1 text-[11px] text-slate-500">
                      {name}
                      {"choices" in (entry?.params[name] ?? {}) ? (
                        <select
                          value={String(value)}
                          onChange={(e) => setParam(idx, name, e.target.value)}
                          className={inputCls}
                        >
                          {(entry!.params[name].choices ?? []).map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={typeof value === "number" || !isNaN(Number(value)) ? "number" : "text"}
                          step="any"
                          value={
                            typeof value === "object" && value !== null && "var" in value
                              ? `$${value.var}`
                              : String(value)
                          }
                          onChange={(e) => setParam(idx, name, e.target.value)}
                          className={`${inputCls} w-20`}
                        />
                      )}
                    </label>
                  ))}
                </div>
                <button
                  onClick={() => onChange(definition.filter((_, i) => i !== idx))}
                  className="ml-1 rounded px-1.5 py-0.5 text-xs text-slate-300 hover:bg-red-50 hover:text-red-500"
                  title="Remove indicator"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      )}
      <p className="text-[10px] text-slate-400">
        Tip: type a param as <code>$name</code> to bind it to a strategy variable.
      </p>
    </div>
  );
}
