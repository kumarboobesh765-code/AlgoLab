"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { NAV_SECTIONS, type NavSection, type NavItem } from "@/lib/nav";
import { NavIconGlyph } from "@/components/layout/NavIcon";

function BadgePill({ badge }: { badge: NavItem["badge"] }) {
  if (!badge) return null;
  if (badge === "new")
    return (
      <span className="rounded bg-emerald-100 px-1.5 py-px text-[9px] font-semibold uppercase text-emerald-700">
        New
      </span>
    );
  if (badge === "beta")
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

function MegaMenuLink({
  item,
  onNavigate,
  dense,
}: {
  item: NavItem;
  onNavigate: () => void;
  dense?: boolean;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className="group flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-slate-50"
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors group-hover:border-blue-200 group-hover:bg-blue-50 group-hover:text-blue-600">
        {item.icon && <NavIconGlyph icon={item.icon} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-slate-800 group-hover:text-blue-700">
            {item.label}
          </span>
          <BadgePill badge={item.badge} />
        </span>
        {item.description && !dense && (
          <span className="mt-0.5 block text-[11px] leading-snug text-slate-500">
            {item.description}
          </span>
        )}
      </span>
    </Link>
  );
}

function PinnedRow({
  items,
  onNavigate,
}: {
  items: NavItem[];
  onNavigate: () => void;
}) {
  if (!items.length) return null;
  return (
    <div className="border-b border-slate-100 bg-gradient-to-r from-blue-50/40 to-violet-50/40 px-3 py-2.5">
      <p className="px-1 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-blue-600/70">
        Quick actions
      </p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((it) => (
          <Link
            key={it.href + it.label}
            href={it.href}
            onClick={onNavigate}
            className="group inline-flex items-center gap-1.5 rounded-md border border-blue-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-blue-700 transition-colors hover:border-blue-300 hover:bg-blue-50"
          >
            {it.icon && <NavIconGlyph icon={it.icon} className="h-3.5 w-3.5" />}
            <span>{it.label}</span>
            <svg
              className="h-3 w-3 text-blue-400 group-hover:translate-x-0.5 transition-transform"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        ))}
      </div>
    </div>
  );
}

function MegaMenu({
  section,
  onNavigate,
}: {
  section: NavSection;
  onNavigate: () => void;
}) {
  const items = section.items;
  const midpoint = Math.ceil(items.length / 2);
  const left = items.slice(0, midpoint);
  const right = items.slice(midpoint);

  return (
    <div className="min-w-[560px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
      <div className="grid grid-cols-1 gap-1 p-2 sm:grid-cols-2">
        <div>
          {left.map((item) => (
            <MegaMenuLink
              key={item.href + item.label}
              item={item}
              onNavigate={onNavigate}
            />
          ))}
        </div>
        <div>
          {right.map((item) => (
            <MegaMenuLink
              key={item.href + item.label}
              item={item}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      </div>
      {section.pinned && section.pinned.length > 0 && (
        <PinnedRow items={section.pinned} onNavigate={onNavigate} />
      )}
    </div>
  );
}

function CategoryDropdown({
  section,
}: {
  section: NavSection;
}) {
  const [open, setOpen] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pathname = usePathname();
  const active = section.items.some(
    (item) => (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)),
  );

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
        className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
          active
            ? "text-blue-600"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        }`}
        aria-expanded={open}
        aria-haspopup="true"
      >
        {section.icon && <NavIconGlyph icon={section.icon} className="h-4 w-4" />}
        <span>{section.title}</span>
        <svg
          className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div
          className="absolute left-0 top-full z-50 mt-1"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          <div className="mb-1.5 rounded-md bg-slate-900/[0.02] px-1 pt-1">
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              {section.blurb}
            </p>
          </div>
          <MegaMenu section={section} onNavigate={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}

function MobileMenu({ onClose }: { onClose: () => void }) {
  const pathname = usePathname();
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} />
      <aside className="fixed inset-y-0 left-0 z-50 w-80 bg-white shadow-xl overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <Link href="/" onClick={onClose} className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 font-bold text-white text-sm">
              SL
            </div>
            <span className="text-sm font-bold text-slate-900 tracking-tight">StrategyLab</span>
          </Link>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:text-slate-600">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <nav className="px-3 py-4">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className="mb-5">
              <div className="flex items-center gap-2 px-3 pb-1.5">
                {section.icon && (
                  <span className="text-slate-400">
                    <NavIconGlyph icon={section.icon} className="h-3.5 w-3.5" />
                  </span>
                )}
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                  {section.title}
                </p>
              </div>
              {section.pinned && section.pinned.length > 0 && (
                <div className="mb-1.5 space-y-0.5">
                  {section.pinned.map((it) => (
                    <Link
                      key={it.href + it.label}
                      href={it.href}
                      onClick={onClose}
                      className="flex items-center gap-2 rounded-md bg-blue-50 px-3 py-1.5 text-[12px] font-medium text-blue-700 hover:bg-blue-100"
                    >
                      {it.icon && <NavIconGlyph icon={it.icon} className="h-3.5 w-3.5" />}
                      <span>{it.label}</span>
                    </Link>
                  ))}
                </div>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const active =
                    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href + item.label}
                      href={item.href}
                      onClick={onClose}
                      className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] transition-colors ${
                        active
                          ? "bg-blue-50 font-medium text-blue-600"
                          : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                      }`}
                    >
                      {item.icon && (
                        <span className="text-slate-400">
                          <NavIconGlyph icon={item.icon} className="h-4 w-4" />
                        </span>
                      )}
                      <span className="flex-1">{item.label}</span>
                      <BadgePill badge={item.badge} />
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>
    </div>
  );
}

export function Header({ onMobileMenuOpen }: { onMobileMenuOpen: () => void }) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-6">
        <div className="flex items-center gap-4">
          <button
            onClick={onMobileMenuOpen}
            className="lg:hidden p-1.5 text-slate-500 hover:bg-slate-100 rounded-md"
            aria-label="Open menu"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 font-bold text-white text-sm">
              SL
            </div>
            <span className="hidden sm:inline text-sm font-bold text-slate-900 tracking-tight">
              StrategyLab
            </span>
          </Link>
        </div>

        <nav className="hidden lg:flex items-center gap-0.5">
          {NAV_SECTIONS.map((section) => (
            <CategoryDropdown key={section.title} section={section} />
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-500 ring-1 ring-inset ring-slate-200 sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
            V1
          </span>
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

function UserMenu() {
  return (
    <div className="hidden sm:flex items-center gap-2">
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
  );
}

export { MobileMenu };
