import type { ReactNode } from "react";

import "./sections.css";

/**
 * Actions d'en-tête de section (`<SectionCard actions={<SectionActions>…</SectionActions>}>`) : la première
 * est l'action principale (bouton plein), les suivantes sont rendues en secondaire (boutons de création
 * `QuickForm`, autres `.btn.primary`). Passe à la ligne proprement sur mobile.
 */
export function SectionActions({ children }: { children: ReactNode }) {
  return <div className="section-actions">{children}</div>;
}
