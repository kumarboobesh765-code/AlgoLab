# AlgoTest Features (Competitor Feature Inventory)

This document is a feature-by-feature inventory of AlgoTest (https://algotest.in) derived from the public documentation at https://docs.algotest.in. The platform targets Indian F&O and equity traders (NSE/BSE/Delta Exchange crypto) and is built around eight products in three categories:

- **Algo Trading** — Backtest, Algo Trade (live), Forward Test
- **Indicator Algo** — Signals AI, TradingView Signals, Chartink Signals
- **ClickTrade** — Strategy Builder, Simulator

---

## 1. Algo Trading / Backtest

The flagship 920 / Time-Based Algo Trading backtester. The user builds a multi-leg options/equity strategy with no code, runs it against historical tick data, and analyses PnL, drawdown, and risk metrics.

### Core capabilities
- No-code multi-leg strategy builder for options, futures, equities, commodities, and crypto (Delta Exchange)
- Supported backtest sub-modes: Intraday, BTST (Buy Today Sell Tomorrow), Positional, Stock Options, Delta Exchange crypto, and the "920 Straddle" regime-day template
- Strategy import / export (JSON) and a "Recent" list
- Time-based entries (e.g. 09:20, 09:30, candle close) and time-based exits (square-off time)
- Range Breakout leg condition
- Re-entry on SL/Target per leg, with a "No Re-Entry After" time gate
- Overall Momentum filter (uses underlying move vs a time window to suppress bad days)
- Trailing stop loss, lock & trail, lock-in profit target
- Margin estimate before run, and Heatmap visualisation of capital usage / efficiency
- Entry by Exact Strike (vs nearest OTM/ITM)
- Range breakout support and freeze-quantity handling
- Broker Level Settings to override default broker risk caps

### Input controls / parameters
- **Instrument Settings**: underlying (Nifty, BankNifty, FinNifty, Midcap, individual stocks, MCX commodities, Delta crypto), expiry, strike selection (ATM/OTM/ITM, exact strike, % moneyness), lot size, quantity, S/L premium %, freeze quantity
- **Entry & Exit Timing**: entry time, exit time, max-hold duration, partial exits
- **Overall Momentum**: lookback window, threshold %, direction filter
- **Leg Builder**: add/remove legs; per-leg BUY/SELL, quantity, premium-based or points-based SL/Target, target mode (premium/percent/points), trailing SL, re-entry rules
- **Legwise Settings**: target mode, premium/point, trailing, re-entry on SL/Tgt, no re-entry after time, entry by exact strike
- **Overall Strategy Settings**: overall SL, overall Target, overall Trailing SL, Lock & Trail, max trades per day, max loss per day
- **Filters**:
  - DTE (Days-to-Expiry) filter
  - Budget Day filter (only run on macro events)
  - In/Out-of-Sample split (train/test)
- **Date range** and capital baseline
- **Execution mode**: Intraday, BTST, Positional, Delta Exchange
- **Leg count cap**: up to 10 legs in a running strategy

### Output reports & metrics
- **Backtest Results**:
  - Overall Profit
  - Number of Trades
  - Average Profit per Trade
  - Win % / Loss %
  - Average Profit on Winning Trades
  - Average Loss on Losing Trades
  - Max Profit / Max Loss in a Single Trade
  - Max Drawdown + Duration of Max Drawdown
  - Reward-to-Risk Ratio
  - Return / Max DD (annualised)
  - Expectancy, Expectancy Ratio
  - Max Win Streak, Max Losing Streak
  - Max Trades in any Drawdown
  - Slippage metric
- **Compare Backtest**: side-by-side metrics for two strategies
- **In-Out Sample**: train/test split and out-of-sample performance
- **Monte Carlo Drawdown**: bootstrap simulations to estimate DD distribution
- Heatmap of PnL vs parameter combinations

### Portfolio backtest & optimiser
- Run up to 50 strategies in a single portfolio backtest
- Combined PnL, capital curve, drawdown at portfolio level
- Portfolio Import/Export
- Portfolio Optimiser — auto-picks strategy subset to optimise:
  - Win %
  - Average MTM
  - Maximum Drawdown
  - Return / Max Drawdown (RoMaD)
  - Expectancy Ratio
- "Recent Backtests" history list

### Notable extras
- Stock Options backtest mode with continuous (CN) and weekly expiries
- "920 Straddle" template for budget/expiry day straddle strategies
- New regime templates (e.g. high-vol templates for current market)
- Sample strategy library in docs

---

## 2. Algo Trading / Algo Trade (Live Deployment)

Takes a backtested or forward-tested strategy and deploys it to a live broker account.

### Core capabilities
- One-click deployment of any saved strategy to a connected broker
- Multi-broker execution (route to different brokers from one strategy)
- Order slicing to respect freeze quantity per order
- Auto Activation / Auto-Start on day
- Next-Monthly-Rollover support for continuous futures/options
- VEE (Virtual Execution Environment) bridge where broker requires it
- BTST Positional live trading mode

### Live strategy controls
- **Square off** — one-click exit all positions and cancel pendings
- **Switch to Manual** — disconnects AlgoTest from broker so user manages via broker app
- **Add a Leg on the fly** — append a new leg to a running strategy, with per-leg SL/Target/Trail/Re-Entry (cap: 10 legs; Quantity Multiplier does not apply to added legs; Range Breakout disabled for added legs)
- **Square off Individual Leg** — close one leg without disturbing others; behaviour differs by strategy type (Time-Based, Simple Momentum/ORB, Time-Based Iron Fly) and re-entry settings
- **Pause Listening / Start Listening** — toggle new entries & exits
- **Delete** — stop and remove the live deployment
- **Debug / Logs** (under More) — copy debug payload for support; full activity log

### MTM dashboard
- Live MTM graph through the day
- **Show Underlying** overlay to correlate PnL vs spot
- **Min MTM / Max MTM** markers with timestamp
- **Download MTM** as PNG, and minute-wise MTM as CSV

### Trades view (per leg)
- Instrument, Quantity
- Entry Trigger Time, Entry Time, Entry Report Time (broker confirmation)
- Entry Trigger Price, Entry Price
- Initial SL, Updated (trailed) SL, Target
- Exit Trigger Time, Exit Time, Exit Report Time
- Exit Trigger Price, Exit Price
- Underlying value at entry and exit

### Operational views
- **Broker-wise Available & Blocked Margin** (collateral visibility per broker)
- **History (Past Trades)** — long-term trade log
- **Replay Trades** — replay historical live trades against historical tick data
- **Pro View / Execution Dashboard** — for power users monitoring multiple strategies
- **Next Monthly Rollover** calendar
- **Auto Activation** scheduling

### Prerequisites
- Broker connected (multiple supported: Angel One, Zerodha, Dhan, Upstox, Fyers, etc., plus Delta Exchange for crypto)
- Broker algo-trading setup (including VEE) complete
- Daily broker login required (NSE/BSE brokers), not required for Delta Exchange
- Execution Settings configured (qty, order type, auto square-off)

---

## 3. Algo Trading / Forward Test

Paper-trade the same strategy stack on live ticks without risking capital. Used as a validation step between backtest and live.

### Core capabilities
- Run any saved strategy (Backtest-style multi-leg or Signals AI) on a paper account
- Live data, no real orders
- Realistic execution: triggers, SL, Target, Re-Entry, Trailing SL all behave as in live
- Per-strategy Forward Test slot
- One-click conversion Forward Test → Algo Trade when satisfied

### Input controls
- Same leg builder, SL/Target, Re-Entry, No-Re-Entry-After, Range Breakout, Overall Momentum, BTST/Positional mode as Backtest
- Broker selection (uses broker for data feed, not capital)
- Paper capital baseline

### Output reports & metrics
- Intraday PnL, MTM graph
- Number of paper trades, win %, drawdown
- Latency, missed triggers, slippage estimate
- Per-leg trade log (entry/exit times and prices)
- Forward-vs-backtest delta

### Notable extras
- Recommended as a mandatory step before live deployment in AlgoTest's own flow
- Same trade debugging tools (logs, debug payload) as Algo Trade
- Can be deployed from Saved Signals (Signals AI) as well as from Time-Based backtests

---

## 4. Indicator Algo / Signals AI

AI-assisted builder for indicator-based strategies. The user describes or assembles a rule set, validates it, and then deploys to Forward Test or Live.

### Core capabilities
- **AI Agent** — describe a strategy in natural language; the agent generates the indicator logic
- **Canvas** — visual node-based editor to wire up conditions
- **Chart Data** — bar/candle interval selection (1m, 5m, 15m, 1h, 1d, etc.)
- **Rolling vs Fixed Strikes** — choose ATM-rolling strikes or fixed weekly/monthly strikes for options signals
- **Signal Limits** — cooldown between signals, max signals/day, max open signals, daily loss limit

### Indicator library
- **Trend** indicators (EMA, SMA, VWAP, Supertrend, etc.)
- **Momentum** (RSI, MACD, Stochastic, etc.)
- **Volatility** (Bollinger Bands, ATR, IV-based filters)
- Each indicator exposes Parameters (period, source, threshold) for tuning

### Validation
- Backtest the indicator strategy over historical data
- Review PnL, win %, drawdown, max losing streak
- Iterate on the Canvas / Agent prompt until acceptable

### Going Live
- **Saved Signals Dashboard** — manage all created signals
- **Execution Settings** — quantity, order type, product type, auto square-off
- **Forward Test (Paper Trading)** on the same canvas
- **Algo Trade (Live Trading)** — deploy to real broker
- **Pause/Start Listening**, **Debug**, **Logs**, **Delete** controls (same UI as Backtest live)

### Input controls / parameters
- Underlying, expiry, strike logic
- Chart timeframe, indicators, thresholds
- Entry conditions (long, short, both), Exit conditions (SL, target, indicator-based)
- Signal Limits (cooldown, max/day, max open)
- Rolling strike step / Fixed strike selection
- Time filter (only signal between times)

### Output reports & metrics
- Historical signal PnL
- Win rate, profit factor, drawdown
- Time-of-day heatmap of signal wins
- Forward Test live PnL
- Live trade log with entry/exit reasons

### Notable extras
- Independent from the 920 page — Strategies AI's "Algo Trade" runs from Saved Signals, not the 920 deploy page (cross-activating causes confusion / duplicate execution)
- Delta Exchange (crypto) does not require daily broker login
- "How Signals Work" + Troubleshooting / Debug / FAQ in docs
- Glossary and Pricing & Plans pages

---

## 5. Indicator Algo / TradingView Signals

Connect TradingView indicators or strategies to AlgoTest for execution. The user runs the strategy on TradingView, fires an alert webhook, and AlgoTest places the order via broker.

### Core capabilities
- Receive TradingView alert webhooks (TV alerts) in AlgoTest
- Map webhook JSON fields to buy/sell/close actions
- Support for **PineScript** indicator and strategy alerts
- Library of prebuilt / famous TradingView strategies
- Auto square-off at configured time
- Multi-leg options execution triggered by a single TV signal (e.g. spread, straddle, iron fly)

### Setup
- Generate a unique AlgoTest webhook URL
- Paste it into the TradingView alert "Webhook URL" box
- Author the alert message in JSON with ticker, action, qty, etc.
- Configure symbol mapping (TV symbol → AlgoTest instrument)
- Pick a broker and Execution Settings

### Input controls
- TV symbol to AlgoTest instrument map
- Order side (BUY/SELL), quantity, product (MIS/NRML/CNC)
- Order type (MARKET/LIMIT/SL/SL-M)
- Entry time window
- Auto square-off time
- Max trades per day, max loss per day

### Output reports & metrics
- Live PnL, MTM
- Per-signal trade log
- Latency between TV alert and broker order
- Win %, drawdown, profit factor over time
- "Replays" of past TV alerts

### Notable extras
- Troubleshooting page for webhook delivery failures
- PineScript category docs (prebuilt TV scripts)
- Famous Strategies section

---

## 6. Indicator Algo / Chartink Signals

Same model as TradingView Signals, but for Chartink scanners and screener alerts. Suited for users who build stock-screening strategies rather than technical indicators.

### Core capabilities
- Receive Chartink webhook alerts in AlgoTest
- **Multi-stock automation** — a single Chartink alert can trigger AlgoTest to act on all stocks matched in the scan
- Position-level actions: BUY/SELL on equity, futures, or options
- Run equities-only, futures-only, or options-hedged strategies
- Per-symbol Execution Settings

### Setup
- Author a Chartink alert with "Webhook URL" pointing to AlgoTest
- Configure symbol mapping (Chartink symbol → AlgoTest instrument/exchange)
- Set the action (Enter/Exit), product, qty
- Save the signal

### Input controls
- Underlying list (from Chartink scan)
- Side, quantity, product, order type
- Time window to accept signals
- Max positions, max loss per day
- Optional options hedge parameters (strike, expiry, side)

### Output reports & metrics
- Trade log per stock
- Combined PnL across all triggered symbols
- Win %, drawdown, profit factor
- Missed-signal reports (alerts received but no broker action)

### Notable extras
- Can mix with TradingView Signals under the same AlgoTest account
- APIs / Custom Signals: arbitrary JSON webhooks beyond TV/Chartink
- "Advanced Features" docs for custom JSON formats, multi-leg options on equity signals

---

## 7. ClickTrade / Strategy Builder

Discretionary options trading workbench built on a live option chain. The user constructs a position, analyses Greeks and payoff, and then either places a manual trade or sets up alerts/automations.

### Core capabilities
- Live option chain (Nifty, BankNifty, FinNifty, Midcap, individual stocks, MCX)
- One-click multi-leg position building (straddle, strangle, spreads, iron fly, iron condor, calendars, ratio, diagonals, custom)
- Live Greeks: Delta, Theta, Gamma, Vega, IV
- Payoff graph at expiry
- "Edit Greeks" — see how the position changes as spot moves
- Prebuilt templates for common strategies

### Position Dashboard
- Live MTM
- Per-leg LTP, PnL, Greeks
- Combined portfolio Greeks
- Quick adjust / hedge actions

### Margin & collateral
- **Broker-wise Available & Blocked Margin** view
- **Margin view** for the proposed position (estimate vs broker-stated)

### Volatility tools
- **VRP (Volatility Risk Premium) Analysis Tool** — historical realised vs implied, VRP regime chart
- **IVP & IVR** — Implied Volatility Percentile / Rank for the current expiry vs history
- Visual: IV surface, IV cone

### Earnings & event awareness
- **Earnings Calendar** overlay on the option chain — warns about upcoming results that can move IV

### Alerts
- **Strategy Builder Alerts** — set alerts on LTP, Greeks, MTM, time, IV
- Alerts can be linked to: paper-trade simulation, live auto-execution, or Telegram/email notifications
- Manage and edit existing strategies

### Live execution & trade management
- "Multi Broker Execution" — send legs of one strategy to different brokers
- "Live Execution and Trade Management" docs
- Manual square-off, partial exits, roll

### Paper trading & analysis
- "Paper Trading and Analysing" mode — practice without broker
- "Playground" — sandbox to try strategies
- "Position Size Calculator" (also called Edge Calculator)
  - Inputs: Win %, Avg Win, Loss %, Avg Loss
  - Output: Edge per Trade
  - Trade Simulations: starting capital, # of trades, minimum margin → outputs Max Drawdown, Max Losing Streak, halting condition
  - Kelly Sizing (Full Kelly), Fractional Kelly (Half Kelly, 10% Kelly)
  - Skew visualisation: positive skew (low win%, big wins) vs negative skew (high win%, tail risk)

### Setup & management
- Creating and Managing Strategies
- Setting up Strategy Builder
- Introduction / additional information

### Input controls
- Underlying, expiry, strike
- BUY/SELL per leg, qty
- Product (MIS/NRML), order type
- Auto square-off time
- Alert thresholds (LTP, Greek, MTM, time)

### Output reports & metrics
- Live PnL, payoff graph, breakeven points
- Max profit, max loss, margin approx, risk/reward
- POP (Probability of Profit)
- Time decay visualisations

### Notable extras
- ClickTrade Telegram channel for discretionary users
- Volatility course by Raghav Malik (referenced from Position Size Calculator)

---

## 8. ClickTrade / Simulator

A "what-if" playback engine. Replay historical option chains to test discretionary ideas before risking real money. Equivalent to a flight simulator for options traders.

### Core capabilities
- Historical option chain playback (LTP of every strike and expiry at any past minute)
- Choose any past date and time, including volatile events (budget day, election day, RBI policy)
- Build a strategy on the historical chain
- Run the strategy forward in time automatically (Autoplay) or step manually (Manual Simulation)
- See live MTM, Greeks, payoff as the underlying moves

### Setup
- Pick date and time to start simulation
- Select underlying
- Select expiry
- Build legs from the historical option chain (BUY/SELL call/put, strike, qty)
- Apply prebuilt templates (see below)

### Prebuilt strategy templates
- Straddle (long/short)
- Strangle
- Bull Call Spread
- Bear Put Spread
- Iron Fly
- Iron Condor

### Advanced strategies
- Calendar Spread
- Bull Put Spread
- Bear Call Spread
- Ratio Spread
- Diagonal Call / Put
- Futures + Options combined strategies (e.g. synthetic)

### Running a simulation
- **Autoplay**: set playback speed (e.g. "5 minutes per second"); simulation advances through history automatically with live MTM updates; pause/unpause any time
- **Manual Simulation**: step forward by +1m, +5m, +30m, +1h, +1d; or drag the cursor to jump to any time of day
- The Simulator continuously updates PnL, Greeks, and payoff as the simulation runs

### Analysis & adjustment
- Total MTM (realised + unrealised)
- Maximum Profit
- Maximum Loss
- Risk/Reward ratio
- Margin Approx (margin that would be required at the broker)
- Breakeven price(s) — single point or range
- POP (Probability of Profit)
- Payoff Graph
- Greeks panel (Delta, Theta, Gamma, IV, Vega)
- "Advanced Features" for further tweaks

### Input controls
- Start date and time
- Underlying, expiry
- Strikes, sides, qty
- Playback speed
- Step size (manual mode)
- Auto square-off time, target / SL overlays (per leg)

### Output reports & metrics
- Time-stamped MTM curve
- Per-leg LTP and Greeks through the day
- Final PnL, max drawdown
- POP, breakeven
- "What changed" diffs when you adjust the strategy

### Notable extras
- Same option chain UI as Strategy Builder — easy to switch between paper-trading a real chain and replaying history
- Can save and reuse simulator positions
- Useful for "regret testing" — what would have happened if I had held?

---

## Cross-cutting platform features

These appear across multiple products and are part of the platform's overall capability set.

- **Multi-broker support** with broker-specific settings, margin and blocked-margin views
- **VEE (Virtual Execution Environment)** — broker-mandated algo execution bridge
- **Execution Settings** (qty, product, order type, auto square-off, slippage) per strategy
- **RA Algos** — readymade / partner-built algos
- **Error Handling** — central playbook for order failures, broker errors, slippage spikes
- **Free Charts** — Straddle / Strangle live charts (no-login tool)
- **Crypto Trading** — Delta Exchange backtest and live
- **Daily Trades Analysis** — end-of-day MTM and PnL report
- **YouTube Tutorials** — official video walkthroughs
- **Financial Education** — Futures and Options content
- **Blog / Forum** — community + product updates
- **AlgoTest MCP** — Model Context Protocol server for AI assistants
- **Sample Strategy library** and Important Blogs section

---

# Part 2: Quantman.trade Features

[Quantman.trade](https://quantman.trade) is another Indian-options algo platform. Their differentiator is the **Options Basket** (combined-premium chart for multi-leg strategies) — an industry-first claim.

## Core Platform
- 40+ brokers integrated
- 6+ years of historical tick data
- 90+ technical indicators
- Sub-100ms execution
- Web + mobile apps
- Pricing tiers: Basic / Premium / Pro (page renders client-side; full INR prices require a logged-in capture)

## Strategy Builder
- No-code multi-leg options strategy builder
- Options Basket (combined-premium visualization — flagship differentiator)
- Strike selection modes: ATM/OTM/ITM, premium, delta, **strike-multiplier rounding**
- Per-leg **expiry** (calendar spread primitive)
- Re-entry x5 (configurable)
- Lazy leg mode
- Range breakout
- High/Low breakout per leg

## Backtesting
- Years of historical tick-data backtests
- AI-powered strategy suggestions
- Intraday / BTST / Positional / Stock Options modes
- Compare-mode for two strategies
- Optimization (grid + walk-forward)
- 920 Straddle / regime-day templates

## Live Trading
- Multi-broker execution (40+)
- One-click deploy
- Order slicing, freeze-quantity handling
- Risk management (kill switch, daily limits, MTM stops)
- Bracket orders

## Unique / Differentiator Features
- **Options Basket combined-premium chart** (industry-first)
- **Spike Protection timer** — pending SL with manual override
- **Move-to-Cost** — auto-breakeven on counter-leg SL
- **Strike Multiplier** rounding
- **Calendar Spread per-leg expiry** primitive
- **Multi-instrument Advanced Mode** — monitor up to 6 instruments, trade up to 3
- AI-driven strategy suggestions and explanations

---

# Part 3: AlgoLab Feature Audit

## API surface (`apps/api/app/api/v1/`)
- **Auth** — register, login, JWT, guest
- **Strategies** — CRUD, clone, versions, templates, explore
- **Data** — instrument sync, history ingest, quality, status
- **Market** — instruments, candles, option chain (live)
- **Quant** — catalog, validate, preview, scan
- **Backtests** — run, list, detail, replay candles
- **Paper** — accounts CRUD + positions
- **Forward Tests** — create, tick, pause, resume, stop
- **Optimizations** — grid, walk-forward, 2D heatmap
- **Execution** — 7 brokers, OMS, bracket orders, risk, audit, deploy
- **AI** — natural language draft strategy
- **Options** — payoff, Monte Carlo, analytics (Greeks, IV surface, max pain), margin, expired history, backtest
- **Tax** — P&L report + CSV
- **Calendar** — holidays, expiries, cost model, lot validation
- **Automation** — signal loop, paper/confirm/live
- **Polish** — templates, export/import, report, compare

## Frontend pages (`apps/web/src/app/`)
Landing, login, strategies, builder/{visual, flow, legs, technical, ai, templates}, backtest, forward-test, replay, optimization, analytics, scanner, portfolio, reports, explore, tools/{option-chain, option-analytics, payoff-lab, paper-accounts, execution, data-manager, strategy-library, settings, tax-report}

## Backtest engine
- **engine.py** — equity/F&O canonical backtester (next-bar-open, stop-before-target, Indian F&O cost model)
- **options_engine.py** — multi-leg options (Black-Scholes, 15 strike modes, per-leg SL/target/trail/momentum, range breakout, HighLow, daily SL/target, spike protection, move-to-cost, square-off propagation, 10 re-entry modes, lazy legs, expiry gates, auto-roll)

## Schema features (`schema.py`)
- 19 indicators + 6 option Greeks + price sources
- Safe formula parser (no eval)
- ConditionGroup (ALL/ANY, nested)
- Legwise + Overall + RangeBreakout + EntryMomentum + TimeControl configs
- Variable system, indicator references, formula operands

---

# Part 4: Gap Analysis vs. AlgoTest & Quantman

## ✓ Already shipped (in parity with competitors)
- 15 strike selection modes (more than AlgoTest)
- 10 re-entry modes (more than AlgoTest)
- Per-leg momentum, range breakout, HighLow, lazy leg
- Move-to-cost, square-off propagation, daily kill switch, spike protection
- Walk-forward (single split) + grid + 2D heatmap optimization
- 7 brokers live execution
- AI natural-language strategy drafting
- Bracket orders, confirm mode, TWS pending order flow
- Strategy versioning, comparison, import/export
- Indian F&O calendar, cost model, tax report
- SEBI throttle, IP whitelist, audit log
- Paper accounts, forward tests (pause/resume)

## ◐ Partially present
- Walk-forward — single split only; no rolling/expanding window
- Multi-symbol scanner — Greeks + IV surface only; no expiry-chain scanner
- Real-time streaming UI — brokers connected; limited live chart integration
- Portfolio optimization — per-strategy only; no mean-variance/risk-parity
- Strategy marketplace — Explore page exists; no ratings/payment

## ✗ Missing (competitor parity gap)
| # | Feature | Source | Priority | Effort |
|---|---|---|---|---|
| G1 | **Compare two strategies side-by-side** with metric overlay | AlgoTest | P1 | Small |
| G2 | **In/Out-of-Sample split** in backtest report | AlgoTest | P1 | Small |
| G3 | **Monte Carlo Drawdown** bootstrap | AlgoTest | P2 | Medium |
| G4 | **Sensitivity Heatmap visualisation UI** for 2D param | AlgoTest | P2 | Small (API done) |
| G5 | **Portfolio backtest** (run 50 strategies together) | AlgoTest | P1 | Medium |
| G6 | **Portfolio Optimiser** (subset picker by metric) | AlgoTest | P2 | Medium |
| G7 | **Signals AI** — build strategy from prompt, auto-backtest | AlgoTest | P1 | Small (reuse /ai + backtest) |
| G8 | **TradingView webhook receiver** | AlgoTest + Quantman | P1 | Medium |
| G9 | **Chartink webhook receiver** | AlgoTest | P2 | Small |
| G10 | **One-click broker deploy wizard** | AlgoTest | P1 | Small |
| G11 | **Auto Activation / Auto-Start on day** | AlgoTest | P2 | Small |
| G12 | **Switch to Manual** disconnect | AlgoTest | P2 | Small |
| G13 | **Free Charts** (Straddle/Strangle live) | AlgoTest | P3 | Small |
| G14 | **Daily Trades Analysis** end-of-day PnL report | AlgoTest | P2 | Small |
| G15 | **Sample strategy library** (UI on landing) | AlgoTest | P1 | Small |
| G16 | **Options Basket** combined-premium chart | Quantman | P3 | Medium |
| G17 | **Multi-instrument Advanced Mode** (6 monitor / 3 trade) | Quantman | P3 | Large |
| G18 | **Strike Multiplier** rounding | Quantman | P3 | Small |
| G19 | **Public landing page** with 9 product cards | Both | **P1 (this milestone)** | Small |
| G20 | **Mobile-responsive navigation menu** mirroring AlgoTest | AlgoTest | **P1 (this milestone)** | Small |

---

# Part 5: Prioritised Build Plan

## Milestone A — **Public landing + product menu (this PR)** ← CURRENT
Deliver a public-facing landing page with a top nav that mirrors AlgoTest's menu (Algo Trading, Indicator Algo, ClickTrade, Resources + Tools, Pricing, Partnership). Each product gets a card with description + status (Live / Coming soon) linking to the appropriate route. This makes the platform look like a real product to anyone visiting the home page, and gives the user a single menu to navigate to the work items below.

## Milestone B — One-click deploy + Signals AI (1-2 days)
- G10: One-click "Deploy to live" button on every backtest result
- G7: Signals AI page (`/builder/signals-ai`) — combines NL draft + auto-backtest + suggested leg config
- G15: Sample strategy library page (`/library`) on landing

## Milestone C — Compare & Portfolio (2-3 days)
- G1: Compare two strategies side-by-side (equity overlay + metric table)
- G2: In/Out-of-Sample split in backtest detail
- G5: Portfolio backtest (run 50 strategies, combined PnL)
- G4: Sensitivity heatmap UI (API done)

## Milestone D — Webhook receivers (1-2 days)
- G8: TradingView webhook receiver (`POST /webhooks/tradingview`) → trigger strategy
- G9: Chartink webhook receiver (`POST /webhooks/chartink`) → trigger strategy
- G11: Auto Activation / Auto-Start
- G12: Switch to Manual disconnect

## Milestone E — Reporting & polish (1-2 days)
- G3: Monte Carlo Drawdown (bootstrap)
- G6: Portfolio Optimiser subset picker
- G14: Daily Trades Analysis end-of-day report
- G13: Free Charts (Straddle/Strangle) on landing

## Milestone F — Differentiators (3-5 days)
- G16: Options Basket combined-premium chart
- G18: Strike Multiplier rounding
- (G17: Multi-instrument Advanced Mode — large, defer)

---

# Part 6: What to do next

Open question for the user — pick the next milestone once Milestone A is merged. The default recommendation is **Milestone B** (one-click deploy + Signals AI) because both are high-impact and short — they make existing backtests dramatically more useful.

