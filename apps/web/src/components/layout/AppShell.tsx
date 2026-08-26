"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore, useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { useAuth } from "@/lib/auth";
import { isMockMode } from "@/lib/api";
import { PAGE_TITLES } from "@/lib/nav";
import { ToastProvider } from "@/components/ui/Toast";
import { useTheme } from "@/components/ui/ThemeProvider";

const noopSubscribe = () => () => {};

function titleForPathname(pathname: string): string {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  const match = Object.keys(PAGE_TITLES)
    .filter((href) => href !== "/" && pathname.startsWith(href))
    .sort((a, b) => b.length - a.length)[0];
  return match ? PAGE_TITLES[match] : "StrategyLab";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout, offline } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const mock = useSyncExternalStore(
    noopSubscribe,
    () => isMockMode(),
    () => false,
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);

  function toggleMock() {
    const next = !mock;
    window.localStorage.setItem("sl_mock", next ? "1" : "0");
    window.location.reload();
  }

  return (
    <ToastProvider>
      <div className="min-h-screen bg-[#F5F7FA]">
          <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
          <div className="ml-60 flex min-h-screen flex-col lg:ml-60">
            {/* Topbar */}
            <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200 bg-white/90 px-6 backdrop-blur">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="lg:hidden p-2 text-slate-600 hover:bg-slate-100 rounded-md"
                  aria-label="Open menu"
                >
                  <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
                <h1 className="text-sm font-semibold text-slate-800">{titleForPathname(pathname)}</h1>
              </div>
              <div className="flex items-center gap-3">
                <span className="hidden items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200 sm:inline-flex">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                  Research Platform · V1
                </span>
                <button
                  onClick={toggleMock}
                  title="Toggle mock data (no backend needed)"
                  className={`hidden rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset sm:inline-flex ${
                    mock
                      ? "bg-amber-100 text-amber-700 ring-amber-300"
                      : "bg-slate-100 text-slate-600 ring-slate-200"
                  }`}
                >
                  Mock: {mock ? "ON" : "OFF"}
                </button>
                <button
                  onClick={toggleTheme}
                  title="Toggle theme"
                  className="hidden rounded-full p-1.5 text-slate-600 hover:bg-slate-100 ring-1 ring-inset ring-slate-200 sm:inline-flex"
                >
                  {theme === "light" ? (
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                  ) : (
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                  )}
                </button>
                {user ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-600">{user.email}</span>
                    <button
                      onClick={logout}
                      className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50"
                    >
                      Sign out
                    </button>
                  </div>
                ) : (
                  <span className="text-xs text-slate-400">Connecting…</span>
                )}
              </div>
            </header>

            {offline && (
              <div className="border-b border-amber-200 bg-amber-50 px-6 py-2 text-xs text-amber-800">
                API offline — pages can&apos;t load data. Start it with{" "}
                <code className="rounded bg-amber-100 px-1 font-mono">powershell -File start-dev.ps1</code>{" "}
                from the repo root, then refresh.
              </div>
            )}

            <main className="flex-1 px-6 py-5">{children}</main>

            <footer className="border-t border-slate-200 px-6 py-3 text-[11px] text-slate-400">
              StrategyLab — backtests and paper trading are simulations. Historical performance does not
              guarantee future results.
        </footer>
      </div>
    </div>
    </ToastProvider>
  );
}
