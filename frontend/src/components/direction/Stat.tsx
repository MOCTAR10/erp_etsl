import type { ReactNode } from "react";

/** Ligne « libellé … valeur » d'une liste de chiffres (`<dl className="dir-stats">`), valeur alignée à droite. */
export function Stat({ label, value, hint, tone }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "ok" | "warn" | "err" }) {
  return (
    <div className="dir-stat">
      <dt>{label}</dt>
      <dd className={tone ? `tone-${tone}` : undefined}>
        <span className="num">{value}</span>
        {hint ? <span className="dir-stat-hint">{hint}</span> : null}
      </dd>
    </div>
  );
}
