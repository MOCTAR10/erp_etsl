import type { ReactNode } from "react";

/** Carte graphique (wrapper Recharts) — hauteur de graphique imposée. */
export function ChartCard({
  title,
  subtitle,
  actions,
  children,
  className = "",
  height = 220,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  height?: number;
}) {
  return (
    <div className={`card chart-card ${className}`.trim()}>
      {title || subtitle || actions ? (
        <div className="card-header">
          <div>
            {title ? <div className="card-title">{title}</div> : null}
            {subtitle ? <div className="card-sub">{subtitle}</div> : null}
          </div>
          {actions}
        </div>
      ) : null}
      <div style={{ height }}>{children}</div>
    </div>
  );
}