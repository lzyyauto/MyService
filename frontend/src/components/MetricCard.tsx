import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  danger?: boolean;
}

export function MetricCard({ label, value, hint, icon: Icon, danger }: MetricCardProps) {
  return (
    <article className={`metric-card${danger ? " metric-danger" : ""}`}>
      <div className="metric-icon" aria-hidden="true">
        <Icon size={18} />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        {hint && <small>{hint}</small>}
      </div>
    </article>
  );
}
