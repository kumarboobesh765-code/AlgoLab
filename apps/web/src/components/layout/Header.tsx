"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { NAV_SECTIONS } from "@/lib/nav";

function DropdownMenu({
  section,
  active,
  onClose,
}: {
  section: (typeof NAV_SECTIONS)[number];
  active: boolean;
  onClose: () => void;
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
    <div className="relative" onMouseEnter={handleEnter} onMouseLeave={handleLeave}>
      <button
        className={`flex items-center gap-1 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
          active
            ? "text-blue-600"
            : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
        }`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
      >
        {section.title}
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
          className="absolute left-0 top-full z-50 mt-1 min-w-[200px] rounded-lg border border-slate-200 bg-white py-1.5 shadow-lg"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          {section.items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => {
                setOpen(false);
                onClose();
              }}
              className="flex items-center justify-between px-4 py-2 text-[13px] text-slate-600 hover:bg-slate-50 hover:text-slate-900"
            >
              <span>{item.label}</span>
              {item.soon && (
                <span className="rounded bg-slate-100 px-1.5 py-px text-[9px] font-semibold uppercase text-slate-400">
                  Soon
                </span>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function MobileMenu({
  onClose,
}: {
  onClose: () => void;
}) {
  const pathname = usePathname();
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} />
      <aside className="fixed inset-y-0 left-0 z-50 w-72 bg-white shadow-xl overflow-y-auto">
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
            <div key={section.title} className="mb-4">
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                {section.title}
              </p>
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onClose}
                      className={`flex items-center justify-between rounded-md px-3 py-2 text-[13px] transition-colors ${
                        active
                          ? "bg-blue-50 font-medium text-blue-600"
                          : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                      }`}
                    >
                      <span>{item.label}</span>
                      {item.soon && (
                        <span className="rounded bg-slate-100 px-1.5 py-px text-[9px] font-semibold uppercase text-slate-400">
                          Soon
                        </span>
                      )}
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

export function Header({
  onMobileMenuOpen,
}: {
  onMobileMenuOpen: () => void;
}) {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-6">
        {/* Left: hamburger + brand */}
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

        {/* Center: horizontal nav */}
        <nav className="hidden lg:flex items-center gap-1">
          {NAV_SECTIONS.map((section) => {
            const active = section.items.some(
              (item) => (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)),
            );
            return (
              <DropdownMenu
                key={section.title}
                section={section}
                active={active}
                onClose={() => {}}
              />
            );
          })}
        </nav>

        {/* Right: actions */}
        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-500 ring-1 ring-inset ring-slate-200 sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
            V1
          </span>
          <MockToggle />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

function MockToggle() {
  const mock = typeof window !== "undefined"
    ? window.localStorage.getItem("sl_mock") === "1"
    : false;

  function toggle() {
    const next = !mock;
    window.localStorage.setItem("sl_mock", next ? "1" : "0");
    window.location.reload();
  }

  return (
    <button
      onClick={toggle}
      title="Toggle mock data"
      className={`hidden rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset sm:inline-flex ${
        mock
          ? "bg-amber-100 text-amber-700 ring-amber-300"
          : "bg-slate-100 text-slate-500 ring-slate-200"
      }`}
    >
      Mock: {mock ? "ON" : "OFF"}
    </button>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem("sl_theme");
    if (stored === "dark" || stored === "light") {
      if (theme !== stored) setTheme(stored);
    }
  }

  function toggle() {
    const next = theme === "light" ? "dark" : "light";
    window.localStorage.setItem("sl_theme", next);
    document.documentElement.classList.toggle("dark", next === "dark");
    setTheme(next);
  }

  return (
    <button
      onClick={toggle}
      title="Toggle theme"
      className="hidden rounded-full p-1.5 text-slate-500 hover:bg-slate-100 ring-1 ring-inset ring-slate-200 sm:inline-flex"
    >
      {theme === "light" ? (
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      ) : (
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      )}
    </button>
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
