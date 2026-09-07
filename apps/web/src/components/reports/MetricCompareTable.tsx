export interface MetricRow {
  label: string;
  values: (string | number | null | undefined)[];
  tones?: ("green" | "red" | "slate")[];
  highlight?: "best" | "worst" | "none";
  lowerIsBetter?: boolean;
}

interface MetricCompareTableProps {
  rows: MetricRow[];
  headers: string[];
  highlightBest?: boolean;
}

function toneClass(tone: "green" | "red" | "slate" | undefined) {
  if (tone === "green") return "text-emerald-600";
  if (tone === "red") return "text-red-600";
  return "text-slate-700";
}

function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const n = Number(String(v).replace(/[%,₹$+\s]/g, ""));
  return Number.isFinite(n) ? n : null;
}

export function MetricCompareTable({
  rows,
  headers,
  highlightBest = false,
}: MetricCompareTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-2 py-2">Metric</th>
            {headers.map((h) => (
              <th key={h} className="px-2 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => {
            const nums = row.values.map(toNum);
            const valid = nums.filter((n): n is number => n !== null);
            let bestIdx = -1;
            let worstIdx = -1;
            if (highlightBest && valid.length >= 2) {
              const best = row.lowerIsBetter
                ? Math.min(...valid)
                : Math.max(...valid);
              const worst = row.lowerIsBetter
                ? Math.max(...valid)
                : Math.min(...valid);
              bestIdx = nums.findIndex((n) => n === best);
              worstIdx = nums.findIndex((n) => n === worst);
              if (bestIdx === worstIdx) worstIdx = -1;
            }
            return (
              <tr key={row.label}>
                <td className="px-2 py-2 font-medium text-slate-600">
                  {row.label}
                </td>
                {row.values.map((v, i) => {
                  const explicit = row.tones?.[i];
                  let tone: "green" | "red" | "slate" | undefined =
                    explicit ?? "slate";
                  if (
                    highlightBest &&
                    !explicit &&
                    (i === bestIdx || i === worstIdx)
                  ) {
                    tone = i === bestIdx ? "green" : "red";
                  }
                  return (
                    <td
                      key={i}
                      className={`px-2 py-2 tabular-nums ${toneClass(tone)}`}
                    >
                      {v === null || v === undefined || v === "" ? "—" : String(v)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
