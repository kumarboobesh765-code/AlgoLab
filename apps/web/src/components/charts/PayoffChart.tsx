import type { PayoffPoint } from "@/lib/api";

export function inr(n: number | null): string {
  if (n === null) return "Unlimited";
  const a = Math.abs(n);
  const core =
    a >= 1e7 ? `${(a / 1e7).toFixed(2)}Cr` : a >= 1e5 ? `${(a / 1e5).toFixed(2)}L` : a >= 1e3 ? `${(a / 1e3).toFixed(1)}K` : a.toFixed(0);
  return `${n < 0 ? "-₹" : "+₹"}${core}`;
}

export function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function PayoffChart({
  curve,
  spot,
  breakevens,
}: {
  curve: PayoffPoint[];
  spot: number;
  breakevens: number[];
}) {
  const W = 780;
  const H = 300;
  const PAD = { l: 64, r: 18, t: 14, b: 30 };
  if (curve.length < 2) return null;
  const xs = curve.map((c) => c.price);
  const ys = curve.map((c) => c.pnl);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  let ymin = Math.min(0, ...ys);
  let ymax = Math.max(0, ...ys);
  const pad = Math.max((ymax - ymin) * 0.08, 1);
  ymin -= pad;
  ymax += pad;
  const X = (v: number) => PAD.l + ((v - xmin) / (xmax - xmin)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + ((ymax - v) / (ymax - ymin)) * (H - PAD.t - PAD.b);
  const zeroY = Y(0);

  const segs: React.ReactElement[] = [];
  for (let i = 1; i < curve.length; i++) {
    const p0 = curve[i - 1];
    const p1 = curve[i];
    const positive = (p0.pnl + p1.pnl) / 2 >= 0;
    segs.push(
      <polygon
        key={`f${i}`}
        points={`${X(p0.price)},${Y(p0.pnl)} ${X(p1.price)},${Y(p1.pnl)} ${X(p1.price)},${zeroY} ${X(p0.price)},${zeroY}`}
        fill={positive ? "#10b981" : "#ef4444"}
        opacity={0.13}
      />,
    );
    segs.push(
      <line
        key={`l${i}`}
        x1={X(p0.price)}
        y1={Y(p0.pnl)}
        x2={X(p1.price)}
        y2={Y(p1.pnl)}
        stroke={positive ? "#059669" : "#dc2626"}
        strokeWidth={2}
      />,
    );
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <line x1={PAD.l} y1={zeroY} x2={W - PAD.r} y2={zeroY} stroke="#94a3b8" strokeDasharray="4 3" />
      <text x={8} y={zeroY + 4} fontSize={11} fill="#64748b">
        ₹0
      </text>
      <text x={8} y={PAD.t + 10} fontSize={11} fill="#64748b">
        {inr(ymax)}
      </text>
      <text x={8} y={H - PAD.b} fontSize={11} fill="#64748b">
        {inr(ymin)}
      </text>
      {segs}
      {breakevens.map((be) => (
        <g key={be}>
          <circle cx={X(be)} cy={zeroY} r={4} fill="#2563eb" />
          <text x={X(be)} y={H - PAD.b + 14} fontSize={10} fill="#2563eb" textAnchor="middle">
            BE {be.toLocaleString("en-IN")}
          </text>
        </g>
      ))}
      <line x1={X(spot)} y1={PAD.t} x2={X(spot)} y2={H - PAD.b} stroke="#d97706" strokeDasharray="3 3" />
      <text x={X(spot)} y={PAD.t + 2} fontSize={10} fill="#d97706" textAnchor="middle">
        spot {spot.toLocaleString("en-IN")}
      </text>
    </svg>
  );
}
