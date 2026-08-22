<!-- BEGIN:nextjs-agent-rules -->

# StrategyLab Frontend Agent Guide (apps/web)

## Tech stack
- Next.js 16 (App Router), TypeScript, Tailwind v4
- No state management library (React useState/useCallback only)
- No component library (hand-built Card, Badge, MetricCard components)

## Route structure (src/app/)
All routes are client components ("use client") since they fetch from the API.

| Path | Page | Description |
| --- | --- | --- |
| / | Dashboard | API health, metrics, workflow map |
| /strategies | Strategy Library | CRUD + builder picker + version badges |
| /backtest | Backtest | Run form, metrics, equity curve, trade table, history |
| /forward-test | Forward Test | Start/tick/pause/resume/stop lifecycle |
| /optimization | Optimization | Grid search + walk-forward config + results table |
| /builder/visual | Visual Builder | 7-step guided strategy creation |
| /builder/technical | Technical Builder | JSON editor + templates + validate/preview |
| /builder/flow | Strategy Flow | Pipeline visualization with inline editing |
| /tools/data-manager | Data Manager | Sync instruments, ingest history, quality checks |
| /tools/option-chain | Option Chain | CALLS/STRIKE/PUTS grid, ATM highlight |
| /tools/paper-accounts | Paper Accounts | Virtual capital, positions, orders |

## Key shared modules
- `src/lib/api.ts` — Typed API client: `api<T>(path, init)` attaches JWT automatically
- `src/lib/auth.tsx` — AuthProvider + useAuth hook (JWT in localStorage)
- `src/lib/nav.ts` — Navigation structure (NAV_SECTIONS, PAGE_TITLES)
- `src/lib/builders.ts` — Strategy definition types + helpers (emptyDefinition, addIndicatorFromCatalog, etc.)
- `src/lib/builder-workflow.ts` — useBuilderWorkflow hook (catalog, validate, preview, save)

## UI components (src/components/)
- `ui/Card.tsx` — Section card with title/subtitle/actions/children
- `ui/Badge.tsx` — Status badge (tones: green, red, amber, blue, slate)
- `ui/MetricCard.tsx` — Metric display card
- `components/layout/Sidebar.tsx` — Dark navy sidebar with section labels
- `components/dashboard/DashboardView.tsx` — Main dashboard with metrics + workflow

## Builder components (src/components/builder/)
- `OperandEditor.tsx` — Price/constant/variable/indicator operand selection
- `ConditionRow.tsx` — Single condition (left op right) + AddConditionButton
- `ConditionGroupEditor.tsx` — Recursive ALL/ANY groups (depth < 2)
- `IndicatorsEditor.tsx` — Catalog-driven indicator list with param editing
- `MetaPanel.tsx` — Strategy name/description/type/tags
- `ValidationPanel.tsx` — Validation errors + preview panel

## API types (src/lib/api.ts)
All backend types are defined as TypeScript interfaces. Key groups:
- Strategy types (Strategy, StrategyOut)
- Backtest types (BacktestRun, BacktestResults, BacktestTrade, BacktestSummary)
- Paper types (PaperAccount, PaperAccountDetail, PaperPosition, PaperOrder)
- Forward test types (ForwardTestRun, TickResult)
- Optimization types (OptimizationRun, OptimizationResult)
- Quant types (QuantCatalog, IndicatorCatalogEntry, ValidationResponse, PreviewResponse)

## Lint rules (React Compiler)
- No setState inside useEffect body — use .then() callbacks or handler functions
- No unused variables (TypeScript strict)
- Card component uses `actions` prop (not `action`)
- Badge tones: green|red|amber|blue|slate (NOT emerald)

## Build commands
```powershell
npm run lint    # ESLint (react-hooks, next)
npm run build   # type-check + production build
```

## Common pitfalls
1. **Badge tones**: `green` not `emerald`. Build fails with TypeScript error.
2. **PowerShell UTF-8**: Never use Get-Content | Set-Content. Corrupts non-ASCII chars. Use Write tool.
3. **useSearchParams**: Requires Suspense boundary in Next.js 16. Use window.location.search instead for simplicity.
4. **Card prop**: `actions` (ReactNode), not `action`.
5. **Strategy select**: Filter by `definition !== null` when listing strategies for backtest/optimization.

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
