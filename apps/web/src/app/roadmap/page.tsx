const MILESTONES = [
  {
    id: "A",
    title: "Public landing + product menu",
    status: "shipped" as const,
    blurb:
      "Mirrors the AlgoTest navigation: 9 products in 3 categories, mega-menu, hero, 3-column product grid, pricing, partnership. This is what you are looking at.",
  },
  {
    id: "B",
    title: "One-click deploy + Signals AI",
    status: "shipped" as const,
    blurb:
      "One-click 'Deploy to live' or 'Start paper trade' on every backtest result. Signals AI page combines NL prompt + auto-backtest + 6 instant options presets (ATM Straddle, OTM Strangle, Short Straddle, Iron Condor, Bull Call Spread, Bear Put Spread). Public sample-strategy library on the landing.",
  },
  {
    id: "C",
    title: "Compare + Portfolio",
    status: "shipped" as const,
    blurb:
      "Portfolio Backtest page: run up to 10 strategies at once, get combined equity curve + aggregate metrics. Compare page: side-by-side equity overlay chart with % return normalization + metric delta table. Daily P&L page: per-day realized P&L bar chart + cumulative line + CSV export.",
  },
  {
    id: "D",
    title: "Webhook receivers",
    status: "shipped" as const,
    blurb:
      "TradingView and Chartink webhook receiver pages with URL/secret generation, per-endpoint delivery logs, HMAC-SHA256 signature validation, and auto-trigger of forward test on incoming alert.",
  },
  {
    id: "E",
    title: "Reporting & polish",
    status: "shipped" as const,
    blurb:
      "Drawdown Monte Carlo bootstrap (1000-run) on backtest equity curves. Daily Trades Analysis page with P&L heatmap. Straddle/Strangle what-if chart on the landing page (no signup). Strategy report HTML export.",
  },
  {
    id: "F",
    title: "Differentiators",
    status: "shipped" as const,
    blurb:
      "Options Basket combined-premium payoff chart with Black-Scholes expiry + time-value curves, breakeven markers, and combined Greeks. Strike Multiplier rounding primitive added to Leg Builder.",
  },
];

const STATUS_STYLES: Record<string, string> = {
  shipped:
    "border-emerald-200 bg-emerald-50 text-emerald-700",
  next: "border-blue-200 bg-blue-50 text-blue-700",
  planned: "border-slate-200 bg-slate-50 text-slate-500",
};

const STATUS_LABEL: Record<string, string> = {
  shipped: "Shipped",
  next: "Next up",
  planned: "Planned",
};

export default function RoadmapPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-14">
      <h1 className="text-3xl font-bold text-slate-900">Public roadmap</h1>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">
        StrategyLab is being built to be a credible open competitor to AlgoTest.in and
        Quantman.trade. This page shows the next six milestones we are committing to, in priority
        order. The full competitive feature audit lives in the project repo at{" "}
        <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[12px]">ROADMAP.md</code>.
      </p>

      <ol className="mt-8 space-y-4">
        {MILESTONES.map((m) => (
          <li
            key={m.id}
            className="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-700">
                  {m.id}
                </span>
                <h2 className="text-base font-semibold text-slate-900">{m.title}</h2>
              </div>
              <span
                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase ${
                  STATUS_STYLES[m.status]
                }`}
              >
                {STATUS_LABEL[m.status]}
              </span>
            </div>
            <p className="mt-3 text-[13px] leading-relaxed text-slate-600">{m.blurb}</p>
          </li>
        ))}
      </ol>

      <h2 className="mt-12 text-lg font-semibold text-slate-900">Already shipped (in parity)</h2>
      <p className="mt-2 text-[13px] leading-relaxed text-slate-600">
        15 strike-selection modes · 10 re-entry modes · per-leg momentum/range breakout/HighLow ·
        move-to-cost, daily kill switch, spike protection · walk-forward (single split) + grid + 2D
        heatmap optimisation · 7 brokers live · AI natural-language strategy drafting · bracket
        orders, confirm mode, TWS pending-order flow · strategy versioning, comparison,
        import/export · Indian F&amp;O calendar, cost model, tax report · SEBI throttle, IP
        whitelist, audit log · paper accounts, forward tests (pause/resume).
      </p>
    </div>
  );
}
