"use client";

import { useSyncExternalStore, useState } from "react";
import { Header, MobileMenu } from "@/components/layout/Header";
import { useAuth } from "@/lib/auth";
import { isMockMode } from "@/lib/api";
import { ToastProvider } from "@/components/ui/Toast";

const noopSubscribe = () => () => {};

export function AppShell({ children }: { children: React.ReactNode }) {
  const { offline } = useAuth();
  useSyncExternalStore(
    noopSubscribe,
    () => isMockMode(),
    () => false,
  );
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-[#F8FAFC]">
        <Header onMobileMenuOpen={() => setMobileMenuOpen(true)} />
        {mobileMenuOpen && (
          <MobileMenu onClose={() => setMobileMenuOpen(false)} />
        )}

        {offline && (
          <div className="border-b border-amber-200 bg-amber-50 px-6 py-2 text-xs text-amber-800">
            API offline — pages can&apos;t load data. Start it with{" "}
            <code className="rounded bg-amber-100 px-1 font-mono">powershell -File start-dev.ps1</code>{" "}
            from the repo root, then refresh.
          </div>
        )}

        <main className="px-6 py-5">{children}</main>

        <footer className="border-t border-slate-200 px-6 py-3 text-[11px] text-slate-400">
          StrategyLab — backtests and paper trading are simulations. Historical performance does not
          guarantee future results.
        </footer>
      </div>
    </ToastProvider>
  );
}
