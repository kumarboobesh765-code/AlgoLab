"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { useAuth } from "@/lib/auth";
import { isMockMode } from "@/lib/api";
import { PAGE_TITLES } from "@/lib/nav";

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
  const [mock, setMock] = useState(false);

  useEffect(() => {
    setMock(isMockMode());
  }, []);

  function toggleMock() {
    const next = !mock;
    window.localStorage.setItem("sl_mock", next ? "1" : "0");
    window.location.reload();
  }

  return (
    <div className="min-h-screen bg-[#F5F7FA]">
      <Sidebar />
      <div className="ml-60 flex min-h-screen flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200 bg-white/90 px-6 backdrop-blur">
          <h1 className="text-sm font-semibold text-slate-800">{titleForPathname(pathname)}</h1>
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
  );
}
