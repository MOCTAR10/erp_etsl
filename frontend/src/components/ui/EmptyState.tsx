import type { LucideIcon } from "lucide-react";

export function EmptyState({
  label,
  hint,
  icon: Icon,
}: {
  label: string;
  hint?: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="empty-state">
      {Icon ? <Icon size={28} aria-hidden /> : null}
      <div>{label}</div>
      {hint ? <div className="hint muted">{hint}</div> : null}
    </div>
  );
}