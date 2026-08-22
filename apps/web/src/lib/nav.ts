export interface NavItem {
  label: string;
  href: string;
  soon?: boolean; // feature not implemented yet
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Main",
    items: [
      { label: "Dashboard", href: "/" },
      { label: "Strategies", href: "/strategies" },
      { label: "Backtest", href: "/backtest" },
      { label: "Trade Replay", href: "/replay" },
      { label: "Forward Test", href: "/forward-test" },
      { label: "Analytics", href: "/analytics" },
      { label: "Market Scanner", href: "/scanner" },
      { label: "Portfolio", href: "/portfolio" },
      { label: "Reports", href: "/reports" },
    ],
  },
  {
    title: "Build",
    items: [
      { label: "Visual Builder", href: "/builder/visual" },
      { label: "Technical Builder", href: "/builder/technical" },
      { label: "Strategy Flow", href: "/builder/flow" },
      { label: "AI Builder", href: "/builder/ai", soon: true },
      { label: "Templates", href: "/builder/templates", soon: true },
    ],
  },
  {
    title: "Tools",
    items: [
      { label: "Option Chain", href: "/tools/option-chain" },
      { label: "Strategy Library", href: "/tools/strategy-library", soon: true },
      { label: "Data Manager", href: "/tools/data-manager" },
      { label: "Paper Accounts", href: "/tools/paper-accounts" },
      { label: "Optimization", href: "/optimization" },
      { label: "Settings", href: "/tools/settings", soon: true },
    ],
  },
];

export const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  NAV_SECTIONS.flatMap((s) => s.items).map((i) => [i.href, i.label]),
);
