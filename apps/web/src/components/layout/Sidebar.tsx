"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_SECTIONS } from "@/lib/nav";

function NavItemLink({
  label,
  href,
  soon,
  active,
  onClick,
}: {
  label: string;
  href: string;
  soon?: boolean;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={`group flex items-center justify-between rounded-md px-3 py-[7px] text-[13px] transition-colors ${
        active
          ? "bg-blue-600/15 font-medium text-white ring-1 ring-inset ring-blue-500/30"
          : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
      }`}
    >
      <span className="flex items-center gap-2">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            active ? "bg-blue-400" : "bg-slate-600 group-hover:bg-slate-500"
          }`}
        />
        {label}
      </span>
      {soon && (
        <span className="rounded bg-slate-700/60 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-slate-300">
          Soon
        </span>
      )}
    </Link>
  );
}

export function Sidebar({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const pathname = usePathname();

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-[#0B1220] text-slate-300 transform transition-transform duration-300 ease-in-out lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5 border-b border-white/5 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 font-bold text-white">
            SL
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide text-white">STRATEGYLAB</p>
            <p className="text-[10px] uppercase tracking-widest text-slate-500">
              Build · Backtest · Grow
            </p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                {section.title}
              </p>
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavItemLink
                    key={item.href}
                    label={item.label}
                    href={item.href}
                    soon={item.soon}
                    active={
                      item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)
                    }
                    onClick={onClose}
                  />
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer status */}
        <div className="border-t border-white/5 px-5 py-3">
          <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-2 ring-1 ring-inset ring-emerald-500/20">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            </span>
            <div>
              <p className="text-[11px] font-semibold text-emerald-400">PAPER TRADING ONLY</p>
              <p className="text-[10px] text-slate-500">No real orders in V1</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
