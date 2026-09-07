"use client";

import Link from "next/link";
import {
  PRODUCT_CATEGORIES,
  type ProductCategory,
  type ProductItem,
  type ProductStatus,
} from "@/lib/productNav";

const SAMPLE_STRATEGIES = [
  {
    name: "ATM Straddle",
    tag: "S",
    desc: "Buy ATM call + ATM put at start, square off at end of day. Pure vega play.",
    href: "/builder/ai",
  },
  {
    name: "OTM Strangle",
    tag: "G",
    desc: "Buy OTM call + OTM put (500 pts from ATM). Lower premium, wider breakeven.",
    href: "/builder/ai",
  },
  {
    name: "Iron Condor",
    tag: "IC",
    desc: "Sell OTM call spread + sell OTM put spread. Range-bound strategy.",
    href: "/builder/ai",
  },
  {
    name: "Bull Call Spread",
    tag: "BC",
    desc: "Buy ATM call, sell OTM call. Limited risk, limited reward on upside.",
    href: "/builder/ai",
  },
  {
    name: "Bear Put Spread",
    tag: "BP",
    desc: "Buy ATM put, sell OTM put. Profit when price falls below breakeven.",
    href: "/builder/ai",
  },
  {
    name: "Short Straddle",
    tag: "SS",
    desc: "Sell ATM call + ATM put. Collect premium, bounded risk if move is large.",
    href: "/builder/ai",
  },
];

function StatusPill({ status }: { status: ProductStatus }) {
  if (status === "live")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-700 ring-1 ring-inset ring-emerald-200">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Live
      </span>
    );
  if (status === "beta")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-violet-700 ring-1 ring-inset ring-violet-200">
        Beta
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-500 ring-1 ring-inset ring-slate-200">
      Coming soon
    </span>
  );
}

function ProductCard({
  item,
  onClick,
}: {
  item: ProductItem;
  onClick?: () => void;
}) {
  const disabled = item.status === "soon";
  const className =
    "group flex h-full flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md";
  const content = (
    <>
      <div className="flex items-center justify-between">
        <h4 className="text-[14px] font-semibold text-slate-900 group-hover:text-blue-700">
          {item.label}
        </h4>
        <StatusPill status={item.status} />
      </div>
      <p className="text-[12px] leading-relaxed text-slate-500">{item.description}</p>
      <div className="mt-auto pt-2 text-[11px] font-medium text-blue-600 opacity-0 transition-opacity group-hover:opacity-100">
        {disabled ? "Notify me →" : "Open →"}
      </div>
    </>
  );
  if (disabled) {
    return (
      <div className={className + " cursor-not-allowed opacity-70"}>
        {content}
      </div>
    );
  }
  return (
    <Link href={item.href} className={className} onClick={onClick}>
      {content}
    </Link>
  );
}

function CategoryColumn({ category }: { category: ProductCategory }) {
  return (
    <div>
      <div className="mb-3 border-b border-slate-200 pb-2">
        <h3 className="text-[15px] font-semibold text-slate-900">{category.title}</h3>
        <p className="mt-0.5 text-[12px] text-slate-500">{category.blurb}</p>
      </div>
      <div className="space-y-3">
        {category.items.map((item) => (
          <ProductCard key={item.href} item={item} />
        ))}
      </div>
    </div>
  );
}

const STATS = [
  { value: "15+", label: "Strike selection modes" },
  { value: "10", label: "Re-entry modes" },
  { value: "7", label: "Brokers integrated" },
  { value: "100+", label: "Indicators & Greeks" },
];

const PILLARS = [
  {
    title: "Multi-leg options, made simple",
    body:
      "Build Iron Condors, Butterflies, Spreads, Straddles and custom legs with strike selection by premium, delta, ATM/OTM, straddle width, or strike-multiplier rounding.",
  },
  {
    title: "Backtest years of data in seconds",
    body:
      "Indian F&O cost model (STT, exchange, SEBI, GST) baked in. Per-leg SL/target/trail, momentum entry, range breakout, daily kill-switch, spike protection, move-to-cost.",
  },
  {
    title: "From backtest to paper to live",
    body:
      "Forward-test with auto-ticking, switch to a 7-broker live deployment with one click, or stay virtual — bracket orders, confirm mode, and SEBI compliance already wired.",
  },
];

export default function WelcomePage() {
  return (
    <div className="bg-gradient-to-b from-white via-white to-slate-50">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(60%_50%_at_50%_0%,rgba(59,130,246,0.18),transparent_70%)]"
        />
        <div className="mx-auto max-w-6xl px-6 pb-12 pt-16 text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium text-slate-500">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> 9 products · 7 brokers · V1
          </span>
          <h1 className="mt-5 text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            Algo trading for{" "}
            <span className="bg-gradient-to-r from-blue-600 to-violet-600 bg-clip-text text-transparent">
              Indian retail traders
            </span>
            .
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-[15px] leading-relaxed text-slate-600">
            Build, backtest and forward-test multi-leg options strategies without writing a single
            line of code. Go live with 7 brokers in one click, or stay virtual — your call.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/login"
              className="rounded-md bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
            >
              Get started — it&apos;s free
            </Link>
            <Link
              href="/builder/legs"
              className="rounded-md border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Try the Leg Builder
            </Link>
            <Link
              href="/roadmap"
              className="rounded-md px-3 py-2.5 text-sm font-medium text-slate-500 hover:text-slate-900"
            >
              See the public roadmap →
            </Link>
          </div>

          {/* Stats */}
          <div className="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {STATS.map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left"
              >
                <p className="text-2xl font-bold tabular-nums text-slate-900">{s.value}</p>
                <p className="text-[11px] text-slate-500">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* The 3 mega-menu columns — the same products as the AlgoTest nav */}
      <section className="mx-auto max-w-6xl px-6 py-12">
        <div className="mb-6 text-center">
          <h2 className="text-2xl font-bold text-slate-900">9 products. One platform.</h2>
          <p className="mt-2 text-sm text-slate-500">
            Hover the menu in the header for the same view — or browse the cards below.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {PRODUCT_CATEGORIES.map((cat) => (
            <CategoryColumn key={cat.title} category={cat} />
          ))}
        </div>
      </section>

      {/* Three pillars */}
      <section className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          {PILLARS.map((p) => (
            <div
              key={p.title}
              className="rounded-2xl border border-slate-200 bg-white p-6"
            >
              <h3 className="text-[15px] font-semibold text-slate-900">{p.title}</h3>
              <p className="mt-2 text-[13px] leading-relaxed text-slate-600">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Sample strategy library */}
      <section className="mx-auto max-w-6xl px-6 py-12">
        <div className="mb-6 text-center">
          <h2 className="text-2xl font-bold text-slate-900">Sample strategies</h2>
          <p className="mt-2 text-sm text-slate-500">
            One-click presets inside the platform — backtest any of these in 30 seconds.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SAMPLE_STRATEGIES.map((s) => (
            <Link
              key={s.name}
              href="/builder/ai"
              className="group flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-sm"
            >
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 text-xs font-bold text-white">
                {s.tag}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-semibold text-slate-900 group-hover:text-blue-700">
                  {s.name}
                </span>
                <span className="mt-0.5 block text-[11px] leading-snug text-slate-500">
                  {s.desc}
                </span>
              </span>
            </Link>
          ))}
        </div>
        <div className="mt-5 text-center">
          <Link
            href="/builder/ai"
            className="text-sm font-medium text-blue-600 hover:underline"
          >
            Open Signals AI to try them all →
          </Link>
        </div>
      </section>

      {/* CTA strip */}
      <section className="mx-auto max-w-6xl px-6 pb-16">
        <div className="overflow-hidden rounded-2xl bg-gradient-to-r from-blue-600 to-violet-600 p-8 text-white">
          <h2 className="text-2xl font-bold">Ready to test your first strategy?</h2>
          <p className="mt-2 max-w-2xl text-sm text-blue-50">
            Spin up a paper account, build a straddle in 30 seconds, and backtest 6 years of
            intraday data. No broker required.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link
              href="/login"
              className="rounded-md bg-white px-5 py-2.5 text-sm font-semibold text-blue-700 hover:bg-blue-50"
            >
              Create free account
            </Link>
            <Link
              href="/welcome"
              className="rounded-md border border-white/30 px-5 py-2.5 text-sm font-semibold text-white hover:bg-white/10"
            >
              Browse the 9 products
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
