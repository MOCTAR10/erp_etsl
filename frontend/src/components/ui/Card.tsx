import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`.trim()}>{children}</div>;
}

export function SectionCard({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`card ${className}`.trim()}>
      {title || subtitle || actions ? (
        <div className="card-header">
          <div>
            {title ? <div className="card-title">{title}</div> : null}
            {subtitle ? <div className="card-sub">{subtitle}</div> : null}
          </div>
          {actions}
        </div>
      ) : null}
      <div className="card-body">{children}</div>
    </div>
  );
}