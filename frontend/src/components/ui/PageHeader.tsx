import type { ReactNode } from "react";

/**
 * En-tête de page : sur-titre optionnel, titre (h2, filet rouge ETSL), sous-titre,
 * actions alignées à droite du titre (bouton primaire de la page).
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Petit sur-titre discret (rubrique, code module) au-dessus du titre. */
  eyebrow?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow ? <span className="page-eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
        {subtitle ? <p className="sub">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </div>
  );
}
