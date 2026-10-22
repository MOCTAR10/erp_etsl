import { useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

export interface TabDef {
  id: string;
  label: ReactNode;
  /** Contenu rendu seulement quand l'onglet est actif (les requêtes de l'onglet partent à l'ouverture). */
  content: ReactNode;
}

/**
 * Onglets accessibles (motif WAI-ARIA « tabs ») : ← → Début Fin pour passer d'un onglet à l'autre,
 * activation automatique, un seul panneau monté à la fois.
 */
export function Tabs({ tabs, label, initial }: { tabs: TabDef[]; label: string; initial?: string }) {
  const uid = useId();
  const [active, setActive] = useState(initial ?? tabs[0]?.id);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(0, tabs.findIndex((t) => t.id === active));
  const current = tabs[index];
  if (!current) return null;

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const last = tabs.length - 1;
    const keys: Record<string, number> = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last };
    const next = keys[e.key];
    if (next === undefined) return;
    e.preventDefault();
    setActive(tabs[next].id);
    refs.current[next]?.focus();
  };

  return (
    <div className="dir-tabs">
      <div role="tablist" aria-label={label} className="dir-tablist" onKeyDown={onKey}>
        {tabs.map((tab, i) => {
          const selected = i === index;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${uid}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${uid}-panel`}
              tabIndex={selected ? 0 : -1}
              className="dir-tab"
              onClick={() => setActive(tab.id)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${uid}-panel`} aria-labelledby={`${uid}-tab-${current.id}`} className="dir-tabpanel">
        {current.content}
      </div>
    </div>
  );
}
