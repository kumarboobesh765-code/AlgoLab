const TIERS = [
  {
    name: "Free",
    price: "₹0",
    period: "forever",
    blurb: "Try the platform end-to-end with virtual money.",
    features: [
      "Build unlimited strategies (Visual / Technical / Flow / Legs / AI)",
      "Backtest on 6+ years of demo data",
      "Forward-test with 1 paper account",
      "Optimization (grid + walk-forward)",
      "All 7 brokers in demo mode",
    ],
    cta: "Get started",
    href: "/login",
    highlight: false,
  },
  {
    name: "Pro",
    price: "₹999",
    period: "per month",
    blurb: "For active retail algo traders who want real broker execution.",
    features: [
      "Everything in Free",
      "Live execution across 7 brokers",
      "Up to 5 live deployments at once",
      "Webhook receivers (TradingView, Chartink)",
      "SEBI compliance audit + confirm mode",
      "Priority email support",
    ],
    cta: "Start Pro trial",
    href: "/login",
    highlight: true,
  },
  {
    name: "Team",
    price: "Custom",
    period: "contact us",
    blurb: "For prop desks and small funds trading together.",
    features: [
      "Everything in Pro",
      "Multi-user workspace with role-based access",
      "Shared strategy library + version control",
      "Portfolio backtest (up to 50 strategies)",
      "Risk dashboard with VaR / CVaR",
      "Dedicated Slack channel",
    ],
    cta: "Talk to sales",
    href: "/partnership",
    highlight: false,
  },
];

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-14">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-slate-900">Simple, transparent pricing</h1>
        <p className="mt-2 text-sm text-slate-500">
          V1 pricing is intentionally generous. No per-trade commissions, no surprise fees.
        </p>
      </div>
      <div className="mt-10 grid grid-cols-1 gap-5 md:grid-cols-3">
        {TIERS.map((t) => (
          <div
            key={t.name}
            className={`flex flex-col rounded-2xl border p-6 ${
              t.highlight
                ? "border-blue-300 bg-blue-50/50 shadow-md ring-1 ring-blue-200"
                : "border-slate-200 bg-white"
            }`}
          >
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-semibold text-slate-900">{t.name}</h2>
              {t.highlight && (
                <span className="rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-bold uppercase text-white">
                  Most popular
                </span>
              )}
            </div>
            <p className="mt-1 text-[12px] text-slate-500">{t.blurb}</p>
            <p className="mt-4">
              <span className="text-3xl font-bold text-slate-900">{t.price}</span>
              <span className="ml-1 text-[12px] text-slate-500">{t.period}</span>
            </p>
            <ul className="mt-5 space-y-2 text-[13px] text-slate-700">
              {t.features.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <svg
                    className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <a
              href={t.href}
              className={`mt-6 rounded-md px-4 py-2 text-center text-sm font-semibold transition-colors ${
                t.highlight
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {t.cta}
            </a>
          </div>
        ))}
      </div>
      <p className="mt-10 text-center text-[11px] text-slate-400">
        Prices exclusive of GST. SEBI-mandated algo registration (CIR/2025/0000013) is your
        responsibility before going live.
      </p>
    </div>
  );
}
