const STATUS_STYLES: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600 ring-slate-200",
  backtested: "bg-blue-50 text-blue-700 ring-blue-200",
  paper_ready: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  running: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  paused: "bg-amber-50 text-amber-700 ring-amber-200",
  stopped: "bg-red-50 text-red-700 ring-red-200",
  archived: "bg-slate-100 text-slate-400 ring-slate-200",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  backtested: "Backtested",
  paper_ready: "Paper Ready",
  running: "Running",
  paused: "Paused",
  stopped: "Stopped",
  archived: "Archived",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.draft;
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ring-1 ring-inset ${style}`}
    >
      {label}
    </span>
  );
}

export function Badge({
  children,
  tone = "slate",
}: {
  children: React.ReactNode;
  tone?: "slate" | "blue" | "green" | "red" | "amber";
}) {
  const tones = {
    slate: "bg-slate-100 text-slate-600 ring-slate-200",
    blue: "bg-blue-50 text-blue-700 ring-blue-200",
    green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    red: "bg-red-50 text-red-700 ring-red-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
  } as const;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
