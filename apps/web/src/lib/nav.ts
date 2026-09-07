export interface NavItem {
  label: string;
  href: string;
  description?: string;
  badge?: "soon" | "beta" | "new";
  icon?: NavIcon;
}

export type NavIcon =
  | "dashboard"
  | "play"
  | "rocket"
  | "wallet"
  | "trash"
  | "library"
  | "scale"
  | "report"
  | "wrench"
  | "lightning"
  | "flow"
  | "spark"
  | "layers"
  | "templates"
  | "clock"
  | "optimize"
  | "replay"
  | "history"
  | "chart"
  | "scanner"
  | "chain"
  | "analytics"
  | "payoff"
  | "briefcase"
  | "tv"
  | "ink"
  | "logs"
  | "docs"
  | "map"
  | "tag"
  | "settings"
  | "database"
  | "tax"
  | "compare"
  | "forward"
  | "explore";

export interface NavSection {
  title: string;
  icon: NavIcon;
  blurb: string;
  items: NavItem[];
  pinned?: NavItem[]; // shown as a highlighted quick-actions row
}

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Trade",
    icon: "rocket",
    blurb: "Run strategies live, paper-trade, and monitor deployments",
    pinned: [
      { label: "Start paper trade", href: "/forward-test", icon: "play" },
      { label: "Deploy to broker", href: "/tools/execution", icon: "rocket" },
    ],
    items: [
      { label: "Forward Test", href: "/forward-test", description: "Paper-trade live ticks against your strategies", icon: "forward" },
      { label: "Execution", href: "/tools/execution", description: "Deploy, bracket orders, risk panel, audit", icon: "rocket" },
      { label: "Paper Accounts", href: "/tools/paper-accounts", description: "Virtual accounts with virtual capital", icon: "wallet" },
      { label: "Deployments", href: "/tools/execution", description: "Active broker links and SEBI algo IDs", icon: "library" },
    ],
  },
  {
    title: "Strategies",
    icon: "library",
    blurb: "Manage, compare, and audit your strategy library",
    pinned: [
      { label: "New strategy", href: "/builder/legs", icon: "wrench" },
      { label: "Compare", href: "/compare", icon: "scale" },
    ],
    items: [
      { label: "My Strategies", href: "/strategies", description: "Full list with versions, tags, status", icon: "library" },
      { label: "Explore Algos", href: "/explore", description: "Browse 30+ ready-made templates by category", icon: "explore" },
      { label: "Strategy Library", href: "/tools/strategy-library", description: "Import / export, share via link", icon: "templates" },
      { label: "Compare", href: "/compare", description: "Side-by-side equity curves and metrics", icon: "scale" },
      { label: "Reports", href: "/reports", description: "Per-strategy performance and version history", icon: "report" },
      { label: "Daily P&L", href: "/reports/daily-pnl", description: "Per-day realized P&L across all runs", icon: "history" },
    ],
  },
  {
    title: "Build",
    icon: "wrench",
    blurb: "Six ways to build a strategy — from visual drag-drop to NL prompt",
    pinned: [
      { label: "AI Builder", href: "/builder/ai", icon: "spark" },
      { label: "Leg Builder", href: "/builder/legs", icon: "layers" },
    ],
    items: [
      { label: "Visual Builder", href: "/builder/visual", description: "Drag-and-drop blocks for non-coders", icon: "wrench" },
      { label: "Technical Builder", href: "/builder/technical", description: "Indicator-based entry/exit on candlesticks", icon: "chart" },
      { label: "Strategy Flow", href: "/builder/flow", description: "If-this-then-that flow editor for advanced logic", icon: "flow" },
      { label: "Leg Builder", href: "/builder/legs", description: "Multi-leg options with AlgoTest-parity features", icon: "layers" },
      { label: "AI Builder", href: "/builder/ai", description: "Describe in English — get an auto-backtested strategy", icon: "spark" },
      { label: "Templates", href: "/builder/templates", description: "Pre-built strategy templates to start from", icon: "templates" },
    ],
  },
  {
    title: "Backtest",
    icon: "play",
    blurb: "Test strategies against years of historical data",
    pinned: [
      { label: "Run new backtest", href: "/backtest", icon: "play" },
    ],
    items: [
      { label: "Run Backtest", href: "/backtest", description: "Pick a strategy, set range, see results", icon: "play" },
      { label: "Backtest History", href: "/backtest", description: "Browse and re-open all past runs", icon: "history" },
      { label: "Optimization", href: "/optimization", description: "Grid search + walk-forward", icon: "optimize" },
      { label: "Trade Replay", href: "/replay", description: "Step through candles tick by tick", icon: "replay" },
    ],
  },
  {
    title: "Analyze",
    icon: "chart",
    blurb: "Charts, Greeks, market data, and the dashboard",
    pinned: [
      { label: "Dashboard", href: "/", icon: "dashboard" },
      { label: "Payoff Lab", href: "/tools/payoff-lab", icon: "payoff" },
    ],
    items: [
      { label: "Dashboard", href: "/", description: "Overview of strategies, P&L, alerts", icon: "dashboard" },
      { label: "Analytics", href: "/analytics", description: "Monthly returns, drawdown, win rate over time", icon: "analytics" },
      { label: "Market Scanner", href: "/scanner", description: "Intraday OI / volume / IV scans", icon: "scanner" },
      { label: "Option Chain", href: "/tools/option-chain", description: "Live chain with OI, greeks, max pain", icon: "chain" },
      { label: "Option Analytics", href: "/tools/option-analytics", description: "PCR, max pain, IV surface, greeks", icon: "analytics" },
      { label: "Payoff Lab", href: "/tools/payoff-lab", description: "Basket + multi-leg payoff simulator", icon: "payoff" },
      { label: "Portfolio", href: "/portfolio", description: "Combined backtest + paper portfolio", icon: "briefcase" },
    ],
  },
  {
    title: "Signals",
    icon: "lightning",
    blurb: "Webhook receivers and external signal automation",
    items: [
      { label: "TradingView", href: "/tradingview-signals", description: "Forward TradingView alerts as live triggers", icon: "tv" },
      { label: "Chartink", href: "/chartink-signals", description: "Forward Chartink screener alerts as triggers", icon: "ink" },
      { label: "Webhook Logs", href: "/tradingview-signals", description: "Recent delivery activity + status", icon: "logs" },
    ],
  },
  {
    title: "Help",
    icon: "docs",
    blurb: "Docs, account, data, and admin",
    items: [
      { label: "Documentation", href: "/docs", description: "API + builder walkthroughs", icon: "docs" },
      { label: "Roadmap", href: "/roadmap", description: "What shipped, what's next", icon: "map" },
      { label: "Pricing", href: "/pricing", description: "Free, Pro, Team tiers", icon: "tag" },
      { label: "Data Manager", href: "/tools/data-manager", description: "Ingest and manage historical candle data", icon: "database" },
      { label: "Tax Report", href: "/tools/tax-report", description: "FY-wise STCG / LTCG / business income", icon: "tax" },
      { label: "Settings", href: "/tools/settings", description: "Account, broker, alerts, API keys", icon: "settings" },
    ],
  },
];

export const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  NAV_SECTIONS.flatMap((s) => [...s.items, ...(s.pinned ?? [])]).map((i) => [i.href, i.label]),
);
