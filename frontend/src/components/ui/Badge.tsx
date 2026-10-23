import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type BadgeTone = "ok" | "warn" | "err" | "brand" | "accent" | "neutral" | "info";

type Props = {
  tone?: BadgeTone;
  icon?: LucideIcon;
  children?: ReactNode;
  className?: string;
  /** Libellé complet en infobulle (utile quand le texte est tronqué). */
  title?: string;
};

export function Badge({ tone = "brand", icon: Icon, children, className = "", title }: Props) {
  return (
    <span className={`badge ${tone} ${className}`.trim()} title={title}>
      {Icon ? <Icon size={12} strokeWidth={2} aria-hidden /> : null}
      {children !== undefined && children !== null ? <span className="badge-text">{children}</span> : null}
    </span>
  );
}
