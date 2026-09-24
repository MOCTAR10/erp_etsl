import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type BadgeTone = "ok" | "warn" | "err" | "brand" | "accent" | "neutral";

type Props = {
  tone?: BadgeTone;
  icon?: LucideIcon;
  children?: ReactNode;
  className?: string;
};

export function Badge({ tone = "brand", icon: Icon, children, className = "" }: Props) {
  return (
    <span className={`badge ${tone} ${className}`.trim()}>
      {Icon ? <Icon size={12} /> : null}
      {children}
    </span>
  );
}