import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import { Children, useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import { motionTokens } from "../../theme/tokens";
import { itemRefresh } from "../../lib/motion";
import type { ActionDef } from "./ActionBar";
import type { BadgeTone } from "./Badge";
import { Menu } from "./Menu";
import type { MenuEntry } from "./Menu";
import { notify } from "./Toaster";

/**
 * Kanban horizontal : colonnes de largeur fixe (≥ 260 px, étirées si la place le permet) côte à côte,
 * défilement horizontal propre (fondu sur le bord qui cache des colonnes). Avec `label`, la zone défilante
 * devient une région nommée, atteignable au clavier (←/→ font défiler).
 */
export function Board({
  children,
  className = "",
  style,
  label,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  /** Nom accessible de la zone défilante (ex. « Bons de commande par statut »). */
  label?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: false, end: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const max = el.scrollWidth - el.clientWidth;
      const start = el.scrollLeft > 2;
      const end = max - el.scrollLeft > 2;
      setEdges((prev) => (prev.start === start && prev.end === end ? prev : { start, end }));
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    ro?.observe(el);
    if (el.firstElementChild) ro?.observe(el.firstElementChild);
    return () => {
      el.removeEventListener("scroll", update);
      ro?.disconnect();
    };
  }, []);

  return (
    <div
      ref={ref}
      className={`board ${className}`.trim()}
      style={style}
      data-overflow-start={edges.start || undefined}
      data-overflow-end={edges.end || undefined}
      {...(label ? { role: "region", "aria-label": label, tabIndex: 0 } : {})}
    >
      {children}
    </div>
  );
}

export function BoardColumn({
  title,
  count,
  tone = "neutral",
  icon: Icon,
  children,
  delay = 0,
  limit,
  summary,
  emptyLabel,
}: {
  title: ReactNode;
  count?: number;
  /** Tonalité du statut : petite pastille de couleur devant le titre (le compteur reste neutre). */
  tone?: BadgeTone;
  icon?: LucideIcon;
  children?: ReactNode;
  delay?: number;
  /** Conservé pour compatibilité : la largeur des colonnes est désormais fixée par le board. */
  minWidth?: number;
  /** Nombre de cartes affichées avant « Voir plus » (toutes si absent). */
  limit?: number;
  /** Ligne de synthèse sous le titre (ex. total des montants de la colonne). */
  summary?: ReactNode;
  /** Texte de la colonne vide (défaut « Aucun élément »). */
  emptyLabel?: string;
}) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(limit);
  const cards = Children.toArray(children);
  const visible = shown === undefined ? cards : cards.slice(0, shown);
  const hidden = cards.length - visible.length;
  return (
    <motion.section
      initial={{ opacity: 0, y: motionTokens.distance.xs }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: motionTokens.duration.fast, ease: motionTokens.ease.out, delay }}
      className="board-col"
    >
      <div className="board-col-head">
        <span className="title">
          {Icon ? <Icon size={13} aria-hidden /> : <span className={`board-dot ${tone}`} aria-hidden />}
          <span className="board-col-title">{title}</span>
        </span>
        {typeof count === "number" ? <span className="board-count">{count}</span> : null}
      </div>
      {summary ? <div className="board-col-summary">{summary}</div> : null}
      {cards.length === 0 ? <p className="board-empty">{emptyLabel ?? t("listes.board.empty")}</p> : visible}
      {hidden > 0 ? (
        <button type="button" className="btn ghost sm board-more" onClick={() => setShown((shown ?? 0) + (limit ?? 0))}>
          {t("common.showMore", { count: hidden })}
        </button>
      ) : null}
    </motion.section>
  );
}

export function BoardCard({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  // Entrée en fondu court, sans échelle ni `layout` (coût de rendu sur les grands boards).
  return (
    <motion.div
      initial={{ opacity: 0, y: motionTokens.distance.xs }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ ...itemRefresh, delay }}
      className={`task-card ${className}`.trim()}
    >
      {children}
    </motion.div>
  );
}

/**
 * Actions d'une carte (ou d'une ligne) : UNE action principale en bouton secondaire compact, les autres dans
 * le menu « ⋯ » (destructives en rouge, en dernier). Même contrat que `ActionBar` : POST/PATCH sur l'action DRF,
 * `confirm` (window.confirm), `prompt` libre (window.prompt) ou à choix (liste + Confirmer dans la carte) ;
 * succès et refus du serveur notifiés (toast), listes rechargées.
 * `primary` : libellé de l'action à mettre en avant (défaut : la première action non destructive).
 */
export function CardActions({ actions, primary, align = "start" }: { actions: ActionDef[]; primary?: string; align?: "start" | "end" }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useId();
  const [choosing, setChoosing] = useState<ActionDef | null>(null);
  const [choice, setChoice] = useState("");
  const run = useMutation({
    mutationFn: (a: ActionDef) => (a.method === "PATCH" ? api.patch<unknown>(a.path, a.body ?? {}) : api.post<unknown>(a.path, a.body)),
    onSuccess: (_d, a) => {
      setChoosing(null);
      notify.success(t("listes.actions.done", { action: a.label }));
      void qc.invalidateQueries();
    },
    onError: (e, a) => notify.error(t("listes.actions.failed", { action: a.label }), { description: describeError(e) }),
  });
  const withValue = (a: ActionDef, value: string) => run.mutate({ ...a, body: { ...((a.body as object) ?? {}), [a.prompt!.name]: value } });
  const trigger = (a: ActionDef) => {
    if (a.confirm && !window.confirm(a.confirm)) return;
    if (a.prompt?.options) {
      setChoice("");
      setChoosing(a);
      return;
    }
    if (a.prompt) {
      const value = window.prompt(a.prompt.label);
      if (value === null) return;
      withValue(a, value);
      return;
    }
    run.mutate(a);
  };

  if (actions.length === 0) return null;

  if (choosing?.prompt?.options) {
    return (
      <div className="card-actions card-actions--choice" onClick={(e) => e.stopPropagation()}>
        <label className="sr-only" htmlFor={`${uid}-choice`}>
          {choosing.prompt.label}
        </label>
        <select id={`${uid}-choice`} className="control" value={choice} onChange={(e) => setChoice(e.target.value)} autoFocus>
          <option value="">{choosing.prompt.label}</option>
          {choosing.prompt.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <div className="card-actions-row">
          <button type="button" className="btn primary sm" disabled={!choice || run.isPending} onClick={() => withValue(choosing, choice)}>
            {t("actionBar.confirmer")}
          </button>
          <button type="button" className="btn ghost sm" onClick={() => setChoosing(null)}>
            {t("actionBar.annuler")}
          </button>
        </div>
      </div>
    );
  }

  const main = actions.find((a) => a.label === primary) ?? actions.find((a) => a.tone !== "danger");
  const rest = actions.filter((a) => a !== main);
  const others = [...rest.filter((a) => a.tone !== "danger"), ...rest.filter((a) => a.tone === "danger")];
  const items: MenuEntry[] = others.map((a, i) => ({
    id: `${i}-${a.label}`,
    label: a.label,
    danger: a.tone === "danger",
    disabled: run.isPending,
    onSelect: () => trigger(a),
  }));
  const dangerStart = others.findIndex((a) => a.tone === "danger");
  if (dangerStart > 0) items.splice(dangerStart, 0, "separator");

  return (
    <div className={`card-actions${align === "end" ? " card-actions--end" : ""}`} onClick={(e) => e.stopPropagation()}>
      {main ? (
        <button type="button" className="btn ghost sm" disabled={run.isPending} onClick={() => trigger(main)}>
          {main.label}
        </button>
      ) : null}
      {items.length ? <Menu items={items} size="sm" align={align === "end" ? "end" : "start"} /> : null}
    </div>
  );
}
