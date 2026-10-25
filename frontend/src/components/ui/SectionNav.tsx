import { useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";

export interface SectionNavItem {
  /** `id` de l'élément cible dans la page (la section, son `SectionCard`…). */
  id: string;
  label: ReactNode;
  /** Compteur discret après le libellé (ex. nombre de pièces à traiter). */
  count?: number | string;
}

export interface SectionNavProps {
  items: SectionNavItem[];
  /** Nom accessible du `<nav>` (défaut « Sections de la page »). */
  label?: string;
  /**
   * Hauteur réservée au-dessus des sections lors d'un saut (px) ; par défaut la hauteur de la barre elle-même.
   * Sert aussi de haut de la bande d'observation (section « active »).
   */
  offset?: number;
  /** Appelé après un saut vers une section. */
  onNavigate?: (id: string) => void;
}

/** Plus proche ancêtre qui défile verticalement (la zone `.main` de la coquille), sinon le document. */
function scrollParent(el: HTMLElement | null): HTMLElement {
  for (let p = el?.parentElement; p; p = p.parentElement) {
    const { overflowY } = getComputedStyle(p);
    if (overflowY === "auto" || overflowY === "scroll") return p;
  }
  return (document.scrollingElement as HTMLElement | null) ?? document.documentElement;
}

/**
 * Navigation de sections collante, posée juste sous le `PageHeader` d'un écran long : une ancre par section,
 * la section lue est surlignée (`aria-current="location"`) au défilement (IntersectionObserver). Sous 900 px,
 * la barre défile horizontalement et garde l'ancre active visible. Le saut est fluide, instantané si
 * l'utilisateur a demandé moins d'animations ; le focus passe à la section atteinte (lecteurs d'écran, clavier).
 * `<SectionNav items={[{ id: "synthese", label: "Synthèse" }, { id: "factures", label: "Factures", count: 4 }]} />`
 */
export function SectionNav({ items, label, offset, onNavigate }: SectionNavProps) {
  const { t } = useTranslation();
  const reduce = useReducedMotion();
  const navRef = useRef<HTMLElement>(null);
  const [active, setActive] = useState<string | undefined>(items[0]?.id);
  // Pendant un saut demandé, l'observateur ne doit pas « repasser » par les sections traversées.
  const lockUntil = useRef(0);
  const ids = items.map((i) => i.id).join("|");

  const barHeight = useCallback(() => offset ?? (navRef.current?.getBoundingClientRect().height ?? 0) + 8, [offset]);

  // Section active : la première (dans l'ordre de la page) qui coupe la bande haute de la zone visible.
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const targets = ids
      .split("|")
      .map((id) => (id ? document.getElementById(id) : null))
      .filter((el): el is HTMLElement => el !== null);
    if (targets.length === 0) return;
    const visible = new Map<string, boolean>();
    const top = Math.round(barHeight());
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) visible.set(e.target.id, e.isIntersecting);
        if (Date.now() < lockUntil.current) return;
        const first = targets.find((el) => visible.get(el.id));
        if (first) setActive(first.id);
      },
      { rootMargin: `-${top}px 0px -55% 0px`, threshold: 0 },
    );
    targets.forEach((el) => observer.observe(el));

    // Bas de page atteint : la dernière section, souvent trop courte pour entrer dans la bande, devient active.
    const scroller = scrollParent(navRef.current);
    const source: HTMLElement | Window = scroller === document.scrollingElement ? window : scroller;
    const onScroll = () => {
      if (Date.now() < lockUntil.current) return;
      if (scroller.scrollTop > 0 && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2) {
        setActive(targets[targets.length - 1].id);
      }
    };
    source.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer.disconnect();
      source.removeEventListener("scroll", onScroll);
    };
  }, [ids, barHeight]);

  // Sous 900 px (barre défilante) : l'ancre active reste visible dans la barre, sans faire défiler la page.
  useEffect(() => {
    const nav = navRef.current;
    const link = nav?.querySelector<HTMLElement>('[aria-current="location"]');
    const list = nav?.querySelector<HTMLElement>(".ui-sectionnav-list");
    if (!link || !list || list.scrollWidth <= list.clientWidth) return;
    const left = link.offsetLeft - (list.clientWidth - link.offsetWidth) / 2;
    if (typeof list.scrollTo === "function") list.scrollTo({ left: Math.max(0, left), behavior: reduce ? "auto" : "smooth" });
  }, [active, reduce]);

  const go = (e: MouseEvent<HTMLAnchorElement>, id: string) => {
    const target = document.getElementById(id);
    if (!target) return; // ancre native (aucune cible : comportement du navigateur)
    e.preventDefault();
    setActive(id);
    lockUntil.current = Date.now() + (reduce ? 120 : 900);
    const scroller = scrollParent(navRef.current);
    const isDoc = scroller === document.scrollingElement || scroller === document.documentElement;
    const base = isDoc ? 0 : scroller.getBoundingClientRect().top;
    const y = target.getBoundingClientRect().top - base + scroller.scrollTop - barHeight();
    const behavior: ScrollBehavior = reduce ? "auto" : "smooth";
    if (typeof scroller.scrollTo === "function") scroller.scrollTo({ top: Math.max(0, y), behavior });
    // Focus sur la section atteinte (sans second défilement) : le clavier et les lecteurs d'écran suivent.
    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
    onNavigate?.(id);
  };

  if (items.length === 0) return null;
  return (
    <nav ref={navRef} className="ui-sectionnav" aria-label={label ?? t("premiumKit.sectionNav.label")}>
      <ul className="ui-sectionnav-list">
        {items.map((item) => {
          const current = item.id === active;
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className={`ui-sectionnav-link${current ? " is-active" : ""}`}
                aria-current={current ? "location" : undefined}
                onClick={(e) => go(e, item.id)}
              >
                <span>{item.label}</span>
                {item.count !== undefined && item.count !== null && item.count !== "" ? (
                  <span className="ui-sectionnav-count">{item.count}</span>
                ) : null}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
