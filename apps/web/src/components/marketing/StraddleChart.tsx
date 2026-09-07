"use client";

import { useMemo } from "react";

interface StraddleChartProps {
  symbol: "NIFTY" | "BANKNIFTY" | "FINNIFTY" | "SENSEX";
  spot: number;
  daysToExpiry: number;
  volatility: number;
}

function normCdf(x: number): number {
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x) / Math.sqrt(2);
  const t = 1.0 / (1.0 + p * ax);
  const poly = a1 * t + a2 * t * t + a3 * t * t * t + a4 * t * t * t * t + a5 * t * t * t * t * t;
  const y = 1.0 - poly * Math.exp(-ax * ax);
  return 0.5 * (1.0 + sign * y);
}

function bsCall(S: number, K: number, T: number, sigma: number, r = 0.06): number {
  if (T <= 0) return Math.max(0, S - K);
  const d1 = (Math.log(S / K) + (r + (sigma * sigma) / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2);
}

function bsPut(S: number, K: number, T: number, sigma: number, r = 0.06): number {
  if (T <= 0) return Math.max(0, K - S);
  const d1 = (Math.log(S / K) + (r + (sigma * sigma) / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return K * Math.exp(-r * T) * normCdf(-d2) - S * normCdf(-d1);
}

function strikeStep(symbol: string, spot: number): number {
  if (symbol === "BANKNIFTY") return spot < 30000 ? 100 : 100;
  if (symbol === "SENSEX") return 100;
  return 50;
}

function atmStrike(symbol: string, spot: number): number {
  const step = strikeStep(symbol, spot);
  return Math.round(spot / step) * step;
}

export function StraddleChart({ symbol, spot, daysToExpiry, volatility }: StraddleChartProps) {
  const { today, expiry, breakeven, strike, premium, maxLoss } = useMemo(() => {
    const K = atmStrike(symbol, spot);
    const sigma = volatility / 100;
    const T = daysToExpiry > 0 ? daysToExpiry / 365 : 0;
    const call = bsCall(spot, K, T, sigma);
    const put = bsPut(spot, K, T, sigma);
    const straddlePremium = call + put;
    const range = spot * 0.15;
    const points = 80;
    const lo = spot - range;
    const hi = spot + range;
    const today: { x: number; y: number }[] = [];
    const expiry: { x: number; y: number }[] = [];
    for (let i = 0; i <= points; i++) {
      const x = lo + (i / points) * (hi - lo);
      const tNow = T;
      const tCall = bsCall(x, K, tNow, sigma);
      const tPut = bsPut(x, K, tNow, sigma);
      today.push({ x, y: tCall + tPut - straddlePremium });
      expiry.push({ x, y: Math.max(0, x - K) + Math.max(0, K - x) - straddlePremium });
    }
    const breakevens = [K - straddlePremium, K + straddlePremium].sort((a, b) => a - b);
    return {
      today,
      expiry,
      breakeven: breakevens,
      strike: K,
      premium: straddlePremium,
      maxLoss: -straddlePremium,
    };
  }, [symbol, spot, daysToExpiry, volatility]);

  const w = 360;
  const h = 200;
  const padL = 48;
  const padR = 12;
  const padT = 8;
  const padB = 28;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const allX = today.map((p) => p.x);
  const allY = [...today.map((p) => p.y), ...expiry.map((p) => p.y), 0];
  const xMin = Math.min(...allX);
  const xMax = Math.max(...allX);
  const yMin = Math.min(...allY);
  const yMax = Math.max(...allY);
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;

  const x = (v: number) => padL + ((v - xMin) / xSpan) * innerW;
  const y = (v: number) => padT + (1 - (v - yMin) / ySpan) * innerH;
  const zeroY = y(0);

  const path = (pts: { x: number; y: number }[]) =>
    pts
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`)
      .join(" ");

  const yTicks = 4;
  const tickValues = Array.from({ length: yTicks + 1 }, (_, i) => yMin + (ySpan * i) / yTicks);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">ATM Straddle — {symbol}</h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Spot {spot.toLocaleString("en-IN")} · Strike {strike.toLocaleString("en-IN")} ·{" "}
            {daysToExpiry} DTE · IV {volatility}%
          </p>
        </div>
        <div className="rounded-md bg-slate-50 px-2 py-1 text-right">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Premium</p>
          <p className="text-sm font-semibold tabular-nums text-slate-800">
            ₹{premium.toFixed(0)}
          </p>
        </div>
      </div>

      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Straddle payoff diagram">
        {tickValues.map((tv, i) => (
          <g key={`y-${i}`}>
            <line
              x1={padL}
              y1={y(tv)}
              x2={w - padR}
              y2={y(tv)}
              stroke="#f1f5f9"
              strokeWidth="0.5"
            />
            <text
              x={padL - 6}
              y={y(tv) + 3}
              textAnchor="end"
              fontSize="9"
              fill="#94a3b8"
            >
              {tv.toFixed(0)}
            </text>
          </g>
        ))}

        <line
          x1={padL}
          y1={zeroY}
          x2={w - padR}
          y2={zeroY}
          stroke="#cbd5e1"
          strokeDasharray="3 3"
          strokeWidth="0.8"
        />

        {breakeven.map((be, i) => {
          if (be < xMin || be > xMax) return null;
          return (
            <g key={`be-${i}`}>
              <line
                x1={x(be)}
                y1={padT}
                x2={x(be)}
                y2={h - padB}
                stroke="#a855f7"
                strokeDasharray="3 3"
                strokeWidth="0.8"
              />
              <text
                x={x(be)}
                y={padT + 10}
                textAnchor={i === 0 ? "end" : "start"}
                fontSize="9"
                fill="#7c3aed"
                dx={i === 0 ? -2 : 2}
              >
                BE {be.toFixed(0)}
              </text>
            </g>
          );
        })}

        <line
          x1={x(strike)}
          y1={padT}
          x2={x(strike)}
          y2={h - padB}
          stroke="#dc2626"
          strokeDasharray="2 2"
          strokeWidth="0.7"
        />
        <text x={x(strike)} y={h - padB + 12} textAnchor="middle" fontSize="9" fill="#dc2626">
          {strike}
        </text>

        <path d={path(expiry)} fill="none" stroke="#0ea5e9" strokeWidth="1.8" />
        <path d={path(today)} fill="none" stroke="#8b5cf6" strokeWidth="1.8" />
      </svg>

      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-600">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 bg-sky-500" /> At Expiry (intrinsic)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 bg-violet-500" /> Today (time value)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 bg-red-500" /> Strike
        </span>
        <span className="ml-auto font-medium text-slate-700">
          Max loss: <span className="text-red-600">₹{Math.abs(maxLoss).toFixed(0)}</span>
        </span>
      </div>
    </div>
  );
}
