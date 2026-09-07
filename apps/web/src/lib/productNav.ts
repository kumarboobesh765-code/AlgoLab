/**
 * Public-facing product menu that mirrors the AlgoTest.in navigation:
 *   Algo Trading ▼  |  Indicator Algo ▼  |  ClickTrade ▼
 *   Resources + Tools ▼  |  Pricing  |  Partnership
 *
 * Each item has a status (live / soon) and a category so we can render the
 * 3-column "mega-menu" panel and the public landing page.
 */

export type ProductStatus = "live" | "soon" | "beta";

export interface ProductItem {
  label: string;
  href: string;
  description: string;
  status: ProductStatus;
  icon: "play" | "rocket" | "forward" | "spark" | "tv" | "screen" | "wrench" | "chart";
}

export interface ProductCategory {
  title: string;
  blurb: string;
  items: ProductItem[];
}

export const PRODUCT_CATEGORIES: ProductCategory[] = [
  {
    title: "Algo Trading",
    blurb: "Backtest, deploy, and paper-trade your strategies",
    items: [
      {
        label: "Backtest",
        href: "/backtest",
        status: "live",
        icon: "play",
        description: "Backtest years of data in seconds with detailed reports",
      },
      {
        label: "Algo Trade",
        href: "/tools/execution",
        status: "soon",
        icon: "rocket",
        description: "Deploy algo strategies with one click across 7 brokers",
      },
      {
        label: "Forward Test",
        href: "/forward-test",
        status: "live",
        icon: "forward",
        description: "Trade strategies virtually without risking capital",
      },
    ],
  },
  {
    title: "Indicator Algo",
    blurb: "Turn your indicators, screeners, and prompts into live algos",
    items: [
      {
        label: "Signals AI",
        href: "/builder/ai",
        status: "live",
        icon: "spark",
        description: "Build, backtest and execute strategies with AI",
      },
      {
        label: "TradingView Signals",
        href: "/tradingview-signals",
        status: "soon",
        icon: "tv",
        description: "Automate TradingView indicators, strategies and Pinescripts",
      },
      {
        label: "Chartink Signals",
        href: "/chartink-signals",
        status: "soon",
        icon: "screen",
        description: "Automate your Chartink screeners to take trades",
      },
    ],
  },
  {
    title: "ClickTrade",
    blurb: "Build, analyse and trade directly from the option chain",
    items: [
      {
        label: "Strategy Builder",
        href: "/builder/legs",
        status: "live",
        icon: "wrench",
        description: "Multi-leg options builder with AlgoTest-parity features",
      },
      {
        label: "Simulator",
        href: "/tools/payoff-lab",
        status: "live",
        icon: "chart",
        description: "Simulate your options trading idea with historical data",
      },
    ],
  },
];

export interface ProductLink {
  label: string;
  href: string;
  external?: boolean;
}

export const PRODUCT_LINKS: ProductLink[] = [
  { label: "Pricing", href: "/pricing" },
  { label: "Partnership", href: "/partnership" },
  { label: "Roadmap", href: "/roadmap" },
  { label: "Documentation", href: "/docs" },
];
