"use client";

import type { NavIcon } from "@/lib/nav";

export function NavIconGlyph({ icon, className }: { icon: NavIcon; className?: string }) {
  const cls = className ?? "h-4 w-4";
  const common = { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", className: cls };
  switch (icon) {
    case "dashboard":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M4 13h7V4H4v9zm0 7h7v-5H4v5zm9 0h7V11h-7v9zm0-16v5h7V4h-7z" />
        </svg>
      );
    case "play":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" strokeWidth={1.6} />
          <path d="M10 8.5l5 3.5-5 3.5z" fill="currentColor" stroke="none" />
        </svg>
      );
    case "rocket":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M14 4c4 0 6 2 6 6 0 5-6 10-6 10s-6-5-6-10c0-4 2-6 6-6z" />
          <circle cx="14" cy="10" r="2" strokeWidth={1.6} />
        </svg>
      );
    case "wallet":
      return (
        <svg {...common}>
          <rect x="3" y="6" width="18" height="13" rx="2" strokeWidth={1.6} />
          <path d="M16 12.5h2M3 9h13a3 3 0 013 3v0" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "library":
      return (
        <svg {...common}>
          <rect x="4" y="4" width="4" height="16" rx="1" strokeWidth={1.6} />
          <rect x="10" y="4" width="4" height="16" rx="1" strokeWidth={1.6} />
          <path d="M17 5l3 1-3 14-3-1z" strokeWidth={1.6} strokeLinejoin="round" />
        </svg>
      );
    case "scale":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M12 4v16M4 8l4 8h-8l4-8zm16 0l4 8h-8l4-8z" />
        </svg>
      );
    case "report":
      return (
        <svg {...common}>
          <rect x="5" y="3" width="14" height="18" rx="2" strokeWidth={1.6} />
          <path d="M8 8h8M8 12h8M8 16h5" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "wrench":
      return (
        <svg {...common}>
          <circle cx="9" cy="15" r="4" strokeWidth={1.6} />
          <path d="M13 11l6-6a3 3 0 00-4-4l-6 6" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "lightning":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M13 3L4 14h7l-1 7 9-11h-7l1-7z" />
        </svg>
      );
    case "flow":
      return (
        <svg {...common}>
          <rect x="3" y="3" width="6" height="6" rx="1" strokeWidth={1.6} />
          <rect x="15" y="3" width="6" height="6" rx="1" strokeWidth={1.6} />
          <rect x="9" y="15" width="6" height="6" rx="1" strokeWidth={1.6} />
          <path d="M6 9v3h12V9M12 12v3" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "spark":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M12 3v6M12 15v6M3 12h6M15 12h6M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3" />
        </svg>
      );
    case "layers":
      return (
        <svg {...common}>
          <path strokeLinejoin="round" strokeWidth={1.6} d="M12 3l9 5-9 5-9-5 9-5z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 13l9 5 9-5M3 18l9 5 9-5" />
        </svg>
      );
    case "templates":
      return (
        <svg {...common}>
          <rect x="3" y="3" width="7" height="7" rx="1" strokeWidth={1.6} />
          <rect x="14" y="3" width="7" height="7" rx="1" strokeWidth={1.6} />
          <rect x="3" y="14" width="7" height="7" rx="1" strokeWidth={1.6} />
          <path d="M14 14h7v7" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "clock":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" strokeWidth={1.6} />
          <path strokeLinecap="round" strokeWidth={1.6} d="M12 7v5l3 2" />
        </svg>
      );
    case "optimize":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 18l4-4 4 4 4-8 4 4 2-2" />
          <circle cx="3" cy="18" r="1.4" fill="currentColor" stroke="none" />
          <circle cx="11" cy="14" r="1.4" fill="currentColor" stroke="none" />
          <circle cx="15" cy="6" r="1.4" fill="currentColor" stroke="none" />
        </svg>
      );
    case "replay":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M11 4l-5 5h4a6 6 0 11-6 6" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M8 9h3" />
        </svg>
      );
    case "history":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 12a9 9 0 109-9 9 9 0 00-6.5 2.7L3 8" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 3v5h5" />
          <path strokeLinecap="round" strokeWidth={1.6} d="M12 7v5l3 2" />
        </svg>
      );
    case "chart":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 20h18M5 16l4-4 4 3 6-7" />
        </svg>
      );
    case "scanner":
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="6" strokeWidth={1.6} />
          <path strokeLinecap="round" strokeWidth={1.6} d="M20 20l-4-4" />
        </svg>
      );
    case "chain":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M10 14a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1M14 10a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1" />
        </svg>
      );
    case "analytics":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M4 20V8M10 20V4M16 20v-8M22 20H2" />
        </svg>
      );
    case "payoff":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 20h18M5 16c4-4 6-12 14-12" />
        </svg>
      );
    case "briefcase":
      return (
        <svg {...common}>
          <rect x="3" y="7" width="18" height="13" rx="2" strokeWidth={1.6} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2M3 13h18" />
        </svg>
      );
    case "tv":
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="12" rx="1.5" strokeWidth={1.6} />
          <path d="M8 21h8M12 17v4" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "ink":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M9 11l-5 5v3h3l5-5M9 11l4-4 5 5-4 4M9 11l5 5" />
        </svg>
      );
    case "logs":
      return (
        <svg {...common}>
          <rect x="5" y="3" width="14" height="18" rx="2" strokeWidth={1.6} />
          <path d="M8 8h8M8 12h8M8 16h5" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "docs":
      return (
        <svg {...common}>
          <path strokeLinejoin="round" strokeWidth={1.6} d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9z" />
          <path d="M14 3v6h6M8 13h8M8 17h5" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "map":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M9 4l-6 3v13l6-3 6 3 6-3V4l-6 3-6-3zM9 4v13M15 7v13" />
        </svg>
      );
    case "tag":
      return (
        <svg {...common}>
          <path strokeLinejoin="round" strokeWidth={1.6} d="M20 12L12 4H4v8l8 8z" />
          <circle cx="8" cy="8" r="1.5" fill="currentColor" stroke="none" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" strokeWidth={1.6} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" />
        </svg>
      );
    case "database":
      return (
        <svg {...common}>
          <ellipse cx="12" cy="5" rx="9" ry="3" strokeWidth={1.6} />
          <path d="M3 5v6c0 1.7 4 3 9 3s9-1.3 9-3V5M3 11v6c0 1.7 4 3 9 3s9-1.3 9-3v-6" strokeWidth={1.6} strokeLinecap="round" />
        </svg>
      );
    case "tax":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M9 14l6-6M9 8h.01M15 14h.01" />
          <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth={1.6} />
        </svg>
      );
    case "compare":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 8h6v12M21 16h-6V4M9 8l-3-3-3 3M15 16l3 3 3-3" />
        </svg>
      );
    case "forward":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M4 12h14M14 7l5 5-5 5" />
        </svg>
      );
    case "explore":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" strokeWidth={1.6} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M8 16l2-6 6-2-2 6-6 2z" />
        </svg>
      );
    case "trash":
      return (
        <svg {...common}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M4 7h16M9 7V4h6v3M6 7l1 13a2 2 0 002 2h6a2 2 0 002-2l1-13" />
        </svg>
      );
  }
}
