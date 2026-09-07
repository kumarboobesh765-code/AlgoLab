"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import {
  PRODUCT_CATEGORIES,
  PRODUCT_LINKS,
  type ProductCategory,
  type ProductItem,
} from "@/lib/productNav";

function StatusBadge({ status }: { status: ProductItem["status"] }) {
  if (status === "live") return null;
  if (status === "beta")
    return (
      <span className="rounded bg-violet-100 px-1.5 py-px text-[9px] font-semibold uppercase text-violet-700">
        Beta
      </span>
    );
  return (
    <span className="rounded bg-slate-100 px-1.5 py-px text-[9px] font-semibold uppercase text-slate-400">
      Soon
    </span>
  );
}

function CategoryIcon({ icon }: { icon: ProductItem["icon"] }) {
  // Simple monochrome icon set so the design mirrors the AlgoTest screenshot.
  const cls = "h-5 w-5 text-slate-500";
  switch (icon) {
    case "play":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <circle cx="12" cy="12" r="9" />
          <path d="M10 8.5l5 3.5-5 3.5z" fill="currentColor" stroke="none" />
        </svg>
      );
    case "rocket":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M14 4c4 0 6 2 6 6 0 5-6 10-6 10s-6-5-6-10c0-4 2-6 6-6z" />
          <circle cx="14" cy="10" r="2" />
        </svg>
      );
    case "forward":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M4 12h14M14 7l5 5-5 5" />
        </svg>
      );
    case "spark":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M12 3v6M12 15v6M3 12h6M15 12h6M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3" />
        </svg>
      );
    case "tv":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <rect x="3" y="5" width="18" height="12" rx="1.5" />
          <path d="M8 21h8M12 17v4" />
        </svg>
      );
    case "screen":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <rect x="3" y="4" width="18" height="14" rx="1.5" />
          <path d="M8 21h8M12 18v3" />
          <path d="M7 10h10M7 14h6" />
        </svg>
      );
    case "wrench":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <circle cx="9" cy="15" r="4" />
          <path d="M13 11l6-6a3 3 0 00-4-4l-6 6" />
        </svg>
      );
    case "chart":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <path d="M3 20h18M5 16l4-4 4 3 6-7" />
        </svg>
      );
  }
}

function ProductLink({
  item,
  onNavigate,
}: {
  item: ProductItem;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className="group flex items-start gap-3 rounded-md px-3 py-2.5 hover:bg-slate-50"
    >
      <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white">
        <CategoryIcon icon={item.icon} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-slate-800 group-hover:text-blue-600">
            {item.label}
          </span>
          <StatusBadge status={item.status} />
        </span>
        <span className="mt-0.5 block text-[11px] leading-snug text-slate-500">
          {item.description}
        </span>
      </span>
    </Link>
  );
}

/**
 * Three-column mega-menu panel — exactly the layout the AlgoTest screenshot
 * shows when you hover "Algo Trading" / "Indicator Algo" / "ClickTrade".
 */
function ProductMegaMenu({
  category,
  onNavigate,
}: {
  category: ProductCategory;
  onNavigate: () => void;
}) {
  return (
    <div className="grid min-w-[640px] gap-6 p-5 md:grid-cols-3">
      <div>
        <h3 className="px-1 text-[12px] font-semibold uppercase tracking-wider text-slate-400">
          {category.title}
        </h3>
        <p className="mt-1 px-1 text-[12px] text-slate-500">{category.blurb}</p>
      </div>
      <div className="md:col-span-2 space-y-1">
        {category.items.map((item) => (
          <ProductLink key={item.href} item={item} onNavigate={onNavigate} />
        ))}
      </div>
    </div>
  );
}

function CategoryDropdown({
  category,
}: {
  category: ProductCategory;
}) {
  const [open, setOpen] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleEnter() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpen(true);
  }
  function handleLeave() {
    timeoutRef.current = setTimeout(() => setOpen(false), 150);
  }

  return (
    <div
      className="relative"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 rounded-md px-3 py-1.5 text-[13px] font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
        aria-expanded={open}
      >
        {category.title}
        <svg
          className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div
          className="absolute left-0 top-full z-50 mt-1 rounded-xl border border-slate-200 bg-white shadow-xl"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          <ProductMegaMenu category={category} onNavigate={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}

export function MarketingHeader({
  onMobileMenuOpen,
}: {
  onMobileMenuOpen: () => void;
}) {
  const pathname = usePathname() ?? "/";
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-6">
        <div className="flex items-center gap-4">
          <button
            onClick={onMobileMenuOpen}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden"
            aria-label="Open menu"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <Link href="/welcome" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 text-xs font-bold text-white">
              SL
            </div>
            <span className="hidden text-sm font-bold tracking-tight text-slate-900 sm:inline">
              StrategyLab
            </span>
          </Link>
        </div>

        <nav className="hidden items-center gap-1 lg:flex">
          {PRODUCT_CATEGORIES.map((cat) => (
            <CategoryDropdown key={cat.title} category={cat} />
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 lg:flex">
            {PRODUCT_LINKS.map((link) => {
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
                    active
                      ? "text-blue-600"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
          <Link
            href="/login"
            className="rounded-md px-3 py-1.5 text-[13px] font-medium text-slate-600 hover:bg-slate-100"
          >
            Sign In
          </Link>
          <Link
            href="/login"
            className="rounded-md bg-blue-600 px-3 py-1.5 text-[13px] font-medium text-white hover:bg-blue-700"
          >
            Get Started
          </Link>
        </div>
      </div>
    </header>
  );
}
