import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h2>{title}</h2>
        {subtitle ? <p className="sub">{subtitle}</p> : null}
      </div>
      {actions ? (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>{actions}</div>
      ) : null}
    </div>
  );
}