import { Briefcase, FileSignature, FolderOpen, HardHat, ShoppingCart, UserRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { Paginated } from "../types";
import { canSeeApp, type ErpApp } from "./modules";

/** Ligne de liste DRF vue par la palette : seuls quelques champs d'affichage sont lus. */
export type EntityRow = { id: string | number } & Record<string, unknown>;

/** Source de recherche d'entités de la palette (Ctrl K) : une liste DRF exposant `?search=`. */
export interface EntitySource {
  /** Clé i18n du groupe (`shell.search.<key>`) et préfixe des identifiants. */
  key: string;
  /** Application ERP lue (RF-59) ; absente pour le socle (GED), lisible par tous. */
  app?: ErpApp;
  path: string;
  /** Écran ouvert à la sélection. */
  route: string;
  icon: LucideIcon;
  title: (r: EntityRow) => string;
  detail: (r: EntityRow) => string;
}

const txt = (v: unknown): string => (typeof v === "string" ? v.trim() : typeof v === "number" ? String(v) : "");
const joint = (...parts: unknown[]) => parts.map(txt).filter(Boolean).join(" · ");

/** Sources câblées sur les `search_fields` du backend (code, libellé, tiers…). */
export const ENTITY_SOURCES: EntitySource[] = [
  { key: "bc", app: "achats", path: "/api/achats/orders/", route: "/purchases", icon: ShoppingCart, title: (r) => txt(r.code), detail: (r) => joint(r.supplier_name, r.status_label) },
  { key: "of", app: "operations", path: "/api/operations/ordres/", route: "/operations", icon: HardHat, title: (r) => txt(r.code), detail: (r) => joint(r.label, r.status_label) },
  { key: "affaires", app: "commercial", path: "/api/commercial/affaires/", route: "/pipeline", icon: Briefcase, title: (r) => txt(r.code), detail: (r) => joint(r.title, r.client_name) },
  { key: "contrats", app: "commercial", path: "/api/commercial/contracts/", route: "/pipeline", icon: FileSignature, title: (r) => txt(r.code), detail: (r) => joint(r.client_name, r.affaire_title) },
  {
    key: "salaries",
    app: "rh_paie",
    path: "/api/rh-paie/employes/",
    route: "/rh-paie",
    icon: UserRound,
    title: (r) => txt(r.nom_complet) || joint(r.prenom, r.nom).replace(" · ", " "),
    detail: (r) => joint(r.code, r.fonction),
  },
  { key: "documents", path: "/api/documents/documents/", route: "/documents", icon: FolderOpen, title: (r) => txt(r.title) || txt(r.reference), detail: (r) => txt(r.reference) },
];

export interface EntityHit {
  id: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  route: string;
}

export interface EntityGroup {
  key: string;
  hits: EntityHit[];
}

export type EntityFetcher = (path: string, q: string, signal: AbortSignal) => Promise<Paginated<EntityRow>>;

/**
 * Recherche d'entités en parallèle sur les seules sources lisibles par le rôle (`canSeeApp`, fail-open comme
 * la sidebar) ; une source en erreur (403, réseau) est ignorée sans faire échouer les autres. Le `signal`
 * annule toutes les requêtes en cours si la saisie change.
 */
export async function searchEntities(
  q: string,
  signal: AbortSignal,
  modules: string[] | undefined,
  fetcher: EntityFetcher,
  sources: EntitySource[] = ENTITY_SOURCES,
): Promise<EntityGroup[]> {
  const lisibles = sources.filter((s) => !s.app || canSeeApp(modules, s.app));
  const reponses = await Promise.allSettled(lisibles.map((s) => fetcher(s.path, q, signal)));
  return lisibles
    .map((s, i) => {
      const r = reponses[i];
      const rows = r.status === "fulfilled" ? (r.value?.results ?? []) : [];
      return {
        key: s.key,
        hits: rows
          .map((row) => ({ id: `ent-${s.key}-${row.id}`, label: s.title(row), hint: s.detail(row), icon: s.icon, route: s.route }))
          .filter((h) => h.label),
      };
    })
    .filter((g) => g.hits.length > 0);
}
