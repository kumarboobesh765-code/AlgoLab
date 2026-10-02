import ChartTerminal from "@/components/charts/ChartTerminal";

export const metadata = {
  title: "Chart Terminal",
  description: "Candlesticks, volume and multi-pane indicator overlays",
};

export default function ChartPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Chart Terminal</h1>
        <p className="mt-1 text-sm text-slate-500">
          Candlesticks with volume, and every indicator in the catalog as an overlay or
          its own pane.
        </p>
      </div>
      <ChartTerminal />
    </div>
  );
}