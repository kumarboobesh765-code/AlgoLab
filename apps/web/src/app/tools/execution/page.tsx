"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ExecutionOrder,
  type ExecutionPosition,
  type ExecutionFunds,
  type ExecutionRiskStatus,
  type ExecutionAlgoParent,
  type ExecutionAudit,
  type PlaceOrderRequest,
  type AlgoOrderRequest,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";

const BROKERS = ["mock", "zerodha"];
const EXCHANGES = ["NSE", "BSE", "NFO", "BFO", "MCX"];
const SIDES = ["BUY", "SELL"];
const ORDER_TYPES = ["MARKET", "LIMIT", "SL", "SL-M"];
const ALGOS = ["TWAP", "VWAP", "TRANCHE"];

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function inr(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function statusTone(status: string): "green" | "red" | "amber" | "blue" | "slate" {
  switch (status) {
    case "COMPLETE":
      return "green";
    case "REJECTED":
    case "CANCELLED":
    case "EXPIRED":
      return "red";
    case "PARTIAL":
    case "OPEN":
    case "PENDING":
      return "amber";
    default:
      return "slate";
  }
}

export default function ExecutionPage() {
  const [broker, setBroker] = useState("mock");
  const [brokers, setBrokers] = useState<string[]>([...BROKERS]);
  const [risk, setRisk] = useState<ExecutionRiskStatus | null>(null);
  const [funds, setFunds] = useState<ExecutionFunds | null>(null);
  const [orders, setOrders] = useState<ExecutionOrder[]>([]);
  const [positions, setPositions] = useState<ExecutionPosition[]>([]);
  const [algos, setAlgos] = useState<ExecutionAlgoParent[]>([]);
  const [audit, setAudit] = useState<ExecutionAudit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // order form
  const [symbol, setSymbol] = useState("NIFTY");
  const [exchange, setExchange] = useState("NSE");
  const [side, setSide] = useState("BUY");
  const [orderType, setOrderType] = useState("LIMIT");
  const [quantity, setQuantity] = useState(25);
  const [price, setPrice] = useState(22000);

  // algo form
  const [algoSymbol, setAlgoSymbol] = useState("NIFTY");
  const [algoSide, setAlgoSide] = useState("BUY");
  const [algoQty, setAlgoQty] = useState(300);
  const [algoType, setAlgoType] = useState("TWAP");
  const [algoSlices, setAlgoSlices] = useState(6);

  const refresh = useCallback(async () => {
    try {
      const [b, r, f, o, p, a, au] = await Promise.all([
        api<string[]>("/execution/brokers"),
        api<ExecutionRiskStatus>(`/execution/risk?broker=${broker}`),
        api<ExecutionFunds>(`/execution/funds?broker=${broker}`),
        api<ExecutionOrder[]>(`/execution/orders?broker=${broker}`),
        api<ExecutionPosition[]>(`/execution/positions?broker=${broker}`),
        api<ExecutionAlgoParent[]>(`/execution/algos?broker=${broker}`),
        api<ExecutionAudit[]>(`/execution/audit?broker=${broker}`),
      ]);
      setBrokers(b);
      setRisk(r);
      setFunds(f);
      setOrders(o);
      setPositions(p);
      setAlgos(a);
      setAudit(au);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load execution data");
    }
  }, [broker]);

  useEffect(() => {
    // Initial load: setState happens inside async .then() callbacks in refresh()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  const toggleKill = async () => {
    if (!risk) return;
    setBusy(true);
    try {
      const r = await api<ExecutionRiskStatus>(
        `/execution/risk/kill?broker=${broker}&engaged=${!risk.kill_switch}`,
        { method: "POST" },
      );
      setRisk(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kill switch failed");
    } finally {
      setBusy(false);
    }
  };

  const placeOrder = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: PlaceOrderRequest = {
        broker,
        symbol,
        exchange,
        segment: exchange === "NFO" || exchange === "BFO" ? "OPTIONS" : "EQUITY",
        side,
        order_type: orderType,
        quantity,
        price: orderType === "MARKET" ? 0 : price,
      };
      await api<ExecutionOrder>("/execution/orders/place", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Order failed");
    } finally {
      setBusy(false);
    }
  };

  const placeAlgo = async () => {
    setBusy(true);
    setError(null);
    try {
      const now = new Date();
      const end = new Date(now.getTime() + 30 * 60 * 1000);
      const payload: AlgoOrderRequest = {
        broker,
        symbol: algoSymbol,
        exchange: "NSE",
        segment: "EQUITY",
        side: algoSide,
        order_type: "LIMIT",
        quantity: algoQty,
        price,
        algo: algoType,
        start: now.toISOString(),
        end: end.toISOString(),
        slices: algoSlices,
      };
      await api<ExecutionAlgoParent>("/execution/orders/algo", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await api<ExecutionOrder[]>(`/execution/orders/algo/tick?broker=${broker}`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Algo order failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Execution &amp; Broker Gateway</h1>
          <p className="text-sm text-slate-500">
            Phase 10 — unified broker OMS, pre-trade risk, and execution algos.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={broker}
            onChange={(e) => setBroker(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          >
            {brokers.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
          <button
            onClick={toggleKill}
            disabled={busy || !risk}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              risk?.kill_switch
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            {risk?.kill_switch ? "Kill Switch: ON" : "Kill Switch: OFF"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Equity" value={inr(funds?.equity)} />
        <MetricCard label="Available Cash" value={inr(funds?.available_cash)} />
        <MetricCard label="Used Margin" value={inr(funds?.used_margin)} />
        <MetricCard
          label="Daily P&L"
          value={inr(risk?.daily_pnl)}
          tone={(risk?.daily_pnl ?? 0) >= 0 ? "positive" : "negative"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Place Order" subtitle="Routed through risk guards + audit trail">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Symbol</span>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="rounded-md border border-slate-300 px-2 py-1"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Exchange</span>
              <select
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1"
              >
                {EXCHANGES.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Side</span>
              <select
                value={side}
                onChange={(e) => setSide(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1"
              >
                {SIDES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Type</span>
              <select
                value={orderType}
                onChange={(e) => setOrderType(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1"
              >
                {ORDER_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Quantity</span>
              <input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(Number(e.target.value))}
                className="rounded-md border border-slate-300 px-2 py-1"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Price</span>
              <input
                type="number"
                value={price}
                onChange={(e) => setPrice(Number(e.target.value))}
                disabled={orderType === "MARKET"}
                className="rounded-md border border-slate-300 px-2 py-1 disabled:bg-slate-50"
              />
            </label>
          </div>
          <button
            onClick={placeOrder}
            disabled={busy || risk?.kill_switch}
            className="mt-3 w-full rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {risk?.kill_switch ? "Blocked by kill switch" : "Place Order"}
          </button>
        </Card>

        <Card title="Execution Algo" subtitle="Split parent order into child slices (TWAP/VWAP/Tranche)">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Symbol</span>
              <input
                value={algoSymbol}
                onChange={(e) => setAlgoSymbol(e.target.value.toUpperCase())}
                className="rounded-md border border-slate-300 px-2 py-1"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Side</span>
              <select
                value={algoSide}
                onChange={(e) => setAlgoSide(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1"
              >
                {SIDES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Algo</span>
              <select
                value={algoType}
                onChange={(e) => setAlgoType(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1"
              >
                {ALGOS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Slices</span>
              <input
                type="number"
                value={algoSlices}
                onChange={(e) => setAlgoSlices(Number(e.target.value))}
                className="rounded-md border border-slate-300 px-2 py-1"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Quantity</span>
              <input
                type="number"
                value={algoQty}
                onChange={(e) => setAlgoQty(Number(e.target.value))}
                className="rounded-md border border-slate-300 px-2 py-1"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Price</span>
              <input
                type="number"
                value={price}
                onChange={(e) => setPrice(Number(e.target.value))}
                className="rounded-md border border-slate-300 px-2 py-1"
              />
            </label>
          </div>
          <button
            onClick={placeAlgo}
            disabled={busy || risk?.kill_switch}
            className="mt-3 w-full rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {risk?.kill_switch ? "Blocked by kill switch" : "Create & Release Algo"}
          </button>
        </Card>
      </div>

      <Card title="Orders" subtitle={`${orders.length} tracked`}>
        {orders.length === 0 ? (
          <p className="text-sm text-slate-400">No orders yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1 pr-3">Symbol</th>
                  <th className="py-1 pr-3">Side</th>
                  <th className="py-1 pr-3">Qty</th>
                  <th className="py-1 pr-3">Filled</th>
                  <th className="py-1 pr-3">Price</th>
                  <th className="py-1 pr-3">Status</th>
                  <th className="py-1 pr-3">Tag</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.broker_order_id} className="border-t border-slate-100">
                    <td className="py-1 pr-3 font-medium">{o.symbol}</td>
                    <td className="py-1 pr-3">{o.side}</td>
                    <td className="py-1 pr-3 tabular-nums">{o.quantity}</td>
                    <td className="py-1 pr-3 tabular-nums">{o.filled_quantity}</td>
                    <td className="py-1 pr-3 tabular-nums">{fmt(o.average_price)}</td>
                    <td className="py-1 pr-3">
                      <Badge tone={statusTone(o.status)}>{o.status}</Badge>
                    </td>
                    <td className="py-1 pr-3 text-slate-500">{o.tag ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Positions" subtitle={`${positions.length} open`}>
          {positions.length === 0 ? (
            <p className="text-sm text-slate-400">No open positions.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1 pr-3">Symbol</th>
                    <th className="py-1 pr-3">Qty</th>
                    <th className="py-1 pr-3">Avg</th>
                    <th className="py-1 pr-3">LTP</th>
                    <th className="py-1 pr-3">uP&L</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={`${p.symbol}-${i}`} className="border-t border-slate-100">
                      <td className="py-1 pr-3 font-medium">{p.symbol}</td>
                      <td className="py-1 pr-3 tabular-nums">
                        {p.side === "SELL" ? "-" : ""}
                        {p.quantity}
                      </td>
                      <td className="py-1 pr-3 tabular-nums">{fmt(p.average_price)}</td>
                      <td className="py-1 pr-3 tabular-nums">{fmt(p.last_price)}</td>
                      <td
                        className={`py-1 pr-3 tabular-nums ${
                          p.unrealized_pnl >= 0 ? "text-emerald-600" : "text-red-600"
                        }`}
                      >
                        {inr(p.unrealized_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Active Algos" subtitle={`${algos.length} parent orders`}>
          {algos.length === 0 ? (
            <p className="text-sm text-slate-400">No algo orders.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {algos.map((a) => (
                <li
                  key={a.parent_id}
                  className="flex items-center justify-between border-b border-slate-100 pb-2"
                >
                  <div>
                    <span className="font-medium">{a.symbol}</span>{" "}
                    <Badge tone="blue">{a.algo}</Badge>
                    <span className="ml-1 text-slate-500">
                      {a.side} {a.quantity}
                    </span>
                  </div>
                  <span className="text-slate-500 tabular-nums">
                    {a.released_slices}/{a.total_slices} slices
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Compliance Audit Trail" subtitle="SEBI algo-trading order log">
        {audit.length === 0 ? (
          <p className="text-sm text-slate-400">No audit entries.</p>
        ) : (
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-white text-slate-500">
                <tr>
                  <th className="py-1 pr-3">Time</th>
                  <th className="py-1 pr-3">Action</th>
                  <th className="py-1 pr-3">Detail</th>
                </tr>
              </thead>
              <tbody>
                {audit
                  .slice()
                  .reverse()
                  .map((e, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="py-1 pr-3 text-slate-500">{e.timestamp}</td>
                      <td className="py-1 pr-3 font-medium">{e.action}</td>
                      <td className="py-1 pr-3 text-slate-600">{e.detail}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
