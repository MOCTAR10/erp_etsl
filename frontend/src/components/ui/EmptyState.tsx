import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** État vide unifié : icône discrète, titre court, aide et action optionnelles. */
export function EmptyState({
  label,
  hint,
  icon: Icon,
  action,
  compact = false,
}: {
  label: string;
  hint?: ReactNode;
  icon?: LucideIcon;
  /** Lien ou bouton d'action (ex. « Créer… »). */
  action?: ReactNode;
  /** Variante resserrée (colonne de board, petite carte). */
  compact?: boolean;
}) {
  return (
    <div className={compact ? "empty-state compact" : "empty-state"}>
      {Icon && !compact ? <Icon size={20} strokeWidth={1.75} aria-hidden /> : null}
      <div className="empty-state-title">{label}</div>
      {hint ? <div className="hint muted">{hint}</div> : null}
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}
