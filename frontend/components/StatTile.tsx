export function StatTile({
  label,
  value,
  tone = "default",
  sub,
}: {
  label: string;
  value: string;
  tone?: "default" | "danger" | "warning" | "success";
  sub?: string;
}) {
  const toneColor = {
    default: "var(--text)",
    danger: "var(--danger)",
    warning: "var(--warning)",
    success: "var(--success)",
  }[tone];

  return (
    <div className="panel px-4 py-3 flex flex-col gap-1 min-w-[140px]">
      <span className="text-[11px] uppercase tracking-wide text-[var(--text-dim)]">
        {label}
      </span>
      <span className="mono text-2xl font-semibold" style={{ color: toneColor }}>
        {value}
      </span>
      {sub ? (
        <span className="text-[11px] text-[var(--text-faint)]">{sub}</span>
      ) : null}
    </div>
  );
}
