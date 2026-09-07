interface Series {
  label: string;
  color: string;
  points: { time: string; equity: number }[];
  pctReturn?: boolean;
}

interface EquityCurveChartProps {
  series: Series[];
  showLegend?: boolean;
  height?: number;
  initialReference?: number;
}

function fmtMoney(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e7) return `${(v / 1e7).toFixed(1)}Cr`;
  if (abs >= 1e5) return `${(v / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(0);
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "2-digit" });
}

export function EquityCurveChart({
  series,
  showLegend = true,
  height = 240,
  initialReference,
}: EquityCurveChartProps) {
  const filtered = series.filter((s) => s.points.length >= 2);
  if (filtered.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-xs text-slate-400">
        No equity data to plot.
      </div>
    );
  }

  const isPct = filtered.some((s) => s.pctReturn);
  const w = 760;
  const padL = 56;
  const padR = 12;
  const padT = 8;
  const padB = 28;
  const innerW = w - padL - padR;
  const innerH = height - padT - padB;

  const transformed = filtered.map((s) => {
    if (!s.pctReturn) {
      return { ...s, transformed: s.points };
    }
    const base = s.points[0]?.equity ?? 1;
    const arr = s.points.map((p) => ({
      time: p.time,
      equity: base === 0 ? 0 : ((p.equity - base) / base) * 100,
    }));
    return { ...s, transformed: arr };
  });

  const allValues = transformed.flatMap((s) => s.transformed.map((p) => p.equity));
  let min = Math.min(...allValues);
  let max = Math.max(...allValues);
  if (isPct) {
    min = Math.min(min, 0);
    max = Math.max(max, 0);
  } else {
    const ref = initialReference ?? allValues[0];
    if (typeof ref === "number" && Number.isFinite(ref)) {
      min = Math.min(min, ref);
      max = Math.max(max, ref);
    }
  }
  if (min === max) {
    const pad = isPct ? 1 : Math.max(Math.abs(min) * 0.05, 1);
    min -= pad;
    max += pad;
  }
  const span = max - min;

  const x = (i: number, len: number) => padL + (len <= 1 ? 0 : (i / (len - 1)) * innerW);
  const y = (v: number) => padT + (1 - (v - min) / span) * innerH;

  const refVal = isPct ? 0 : initialReference ?? transformed[0].transformed[0]?.equity ?? 0;
  const refY = y(refVal);

  const ticks = 4;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => min + (span * i) / ticks);

  const allTimes = transformed[0].transformed.map((p) => p.time);
  const xTickIdx = [0, Math.floor((allTimes.length - 1) / 2), allTimes.length - 1];

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${w} ${height}`}
        className="w-full"
        role="img"
        aria-label="Equity curve chart"
      >
        {yTicks.map((v, i) => (
          <g key={`y-${i}`}>
            <line
              x1={padL}
              y1={y(v)}
              x2={w - padR}
              y2={y(v)}
              stroke="#e2e8f0"
              strokeWidth="0.5"
            />
            <text
              x={padL - 6}
              y={y(v) + 3}
              textAnchor="end"
              fontSize="10"
              fill="#94a3b8"
            >
              {isPct ? `${v.toFixed(1)}%` : fmtMoney(v)}
            </text>
          </g>
        ))}

        <line
          x1={padL}
          y1={refY}
          x2={w - padR}
          y2={refY}
          stroke="#cbd5e1"
          strokeDasharray="4 4"
          strokeWidth="1"
        />

        {transformed.map((s) => {
          const pts = s.transformed;
          const path = pts
            .map((p, i) => `${i === 0 ? "M" : "L"}${x(i, pts.length).toFixed(1)},${y(p.equity).toFixed(1)}`)
            .join(" ");
          return (
            <path
              key={s.label}
              d={path}
              fill="none"
              stroke={s.color}
              strokeWidth="1.8"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}

        {xTickIdx.map((i) => {
          if (i >= allTimes.length) return null;
          return (
            <text
              key={`x-${i}`}
              x={x(i, allTimes.length)}
              y={height - 8}
              textAnchor="middle"
              fontSize="10"
              fill="#94a3b8"
            >
              {fmtDate(allTimes[i])}
            </text>
          );
        })}
      </svg>

      {showLegend && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600">
          {transformed.map((s) => {
            const pts = s.transformed;
            const start = pts[0]?.equity ?? 0;
            const end = pts[pts.length - 1]?.equity ?? 0;
            const delta = end - start;
            const sign = delta >= 0 ? "+" : "";
            return (
              <span key={s.label} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-3 rounded-sm"
                  style={{ backgroundColor: s.color }}
                />
                <span className="font-medium text-slate-700">{s.label}</span>
                <span
                  className={delta >= 0 ? "text-emerald-600" : "text-red-600"}
                >
                  {isPct
                    ? `${sign}${delta.toFixed(2)}%`
                    : `${sign}${fmtMoney(delta)}`}
                </span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
