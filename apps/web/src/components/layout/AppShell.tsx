"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore, useState } from "react";
import { Header, MobileMenu } from "@/components/layout/Header";
import { MarketingHeader } from "@/components/marketing/MarketingHeader";
import { useAuth } from "@/lib/auth";
import { isMockMode } from "@/lib/api";
import { ToastProvider } from "@/components/ui/Toast";

const noopSubscribe = () => () => {};

// Paths that use the public-facing marketing chrome instead of the in-app
// developer header. Mirrors the AlgoTest.in-style landing experience.
const MARKETING_PATHS = new Set([
  "/welcome",
  "/pricing",
  "/partnership",
  "/roadmap",
  "/docs",
]);

export function AppShell({ children }: { children: React.ReactNode }) {
  const { offline } = useAuth();
  const pathname = usePathname() ?? "/";
  const isMarketing = MARKETING_PATHS.has(pathname);
  useSyncExternalStore(
    noopSubscribe,
    () => isMockMode(),
    () => false,
  );
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-[#F8FAFC]">
        {isMarketing ? (
          <MarketingHeader onMobileMenuOpen={() => setMobileMenuOpen(true)} />
        ) : (
          <Header onMobileMenuOpen={() => setMobileMenuOpen(true)} />
        )}
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

        <main className={isMarketing ? "" : "px-6 py-5"}>{children}</main>

        <footer className="border-t border-slate-200 px-6 py-3 text-[11px] text-slate-400">
          StrategyLab — backtests and paper trading are simulations. Historical performance does not
          guarantee future results.
        </footer>
      </div>
    </ToastProvider>
  );
}
