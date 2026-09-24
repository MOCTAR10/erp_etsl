import type { ReactNode } from "react";

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="section-title">{children}</h3>;
}