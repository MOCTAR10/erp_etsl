import { FilterX, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { DateRangePicker } from "./DatePicker";
import { Popover } from "./Popover";

/** Critère décrit par l'API (`GET <liste>/filtres/`, `config/filtres.py`) : type, libellé et choix déjà traduits. */
export interface FilterDef {
  champ: string;
  type: "choix" | "fk" | "date" | "nombre" | "bool" | "texte";
  libelle: string;
  choix?: { valeur: string; libelle: string }[];
  parametres?: string[];
}

/** Valeurs saisies, indexées par nom de paramètre d'URL (`status`, `document_date__gte`…). */
export type FilterValues = Record<string, string>;

/** Chaîne de requête des critères renseignés (vides ignorés), à passer en `extra` de `usePagedList`. */
export function filtersToQuery(values: FilterValues): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) if (v.trim()) q.set(k, v.trim());
  return q.toString();
}

/** Libellé servi par l'API sans ses références techniques (« Statut (RF-41) » → « Statut »). */
export function cleanFilterLabel(libelle: string): string {
  return libelle.replace(/\s*\((?:RF|EX|H|RG|CL)-[^)]*\)/g, "").trim();
}

type Liste = { valeur: string; libelle: string }[];

/**
 * Barre de filtres multicritères compacte (EX-G-09) : recherche (`search`) + 3 critères en ligne
 * (`primary`, sinon les 3 premiers) + « Plus de filtres » (fenêtre flottante) pour le reste ; critères combinés en ET.
 * choix / fk / bool → liste ; date → période unique jj/mm/aaaa (`__gte` / `__lte`) ; nombre → bornes ; texte → contient.
 * `options` fournit les valeurs d'une clé étrangère ; `more` ajoute des champs libres dans « Plus de filtres »
 * (`moreKeys` = leurs clés dans `value`, comptées dans le badge).
 */
export function FilterBar({
  defs,
  value,
  onChange,
  options = {},
  idPrefix = "filtre",
  primary,
  search,
  more,
  moreKeys = [],
}: {
  defs: FilterDef[];
  value: FilterValues;
  onChange: (next: FilterValues) => void;
  options?: Record<string, Liste>;
  idPrefix?: string;
  /** Champs affichés en ligne (les autres vont dans « Plus de filtres »). Défaut : les 3 premiers. */
  primary?: string[];
  /** Champ de recherche plein texte placé en tête de barre. */
  search?: ReactNode;
  more?: ReactNode;
  /** Clés de `value` saisies par les champs de `more` (comptées dans le badge « Plus de filtres »). */
  moreKeys?: string[];
}) {
  const { t } = useTranslation();
  const set = (k: string, v: string) => onChange({ ...value, [k]: v });
  const actifs = Object.values(value).filter((v) => v.trim()).length;

  const listeDe = (d: FilterDef): Liste | null =>
    d.type === "choix"
      ? (d.choix ?? [])
      : d.type === "fk"
        ? (options[d.champ] ?? d.choix ?? null)
        : d.type === "bool"
          ? [
              { valeur: "true", libelle: t("ecarts_a1.filtres.oui") },
              { valeur: "false", libelle: t("ecarts_a1.filtres.non") },
            ]
          : null;
  // Clé étrangère sans valeurs fournies : critère masqué.
  const visibles = defs.filter((d) => !(d.type === "fk" && !listeDe(d)));
  const enLigne = primary ? visibles.filter((d) => primary.includes(d.champ)) : visibles.slice(0, 3);
  const autres = visibles.filter((d) => !enLigne.includes(d));
  const champsDe = (d: FilterDef) =>
    d.type === "date" || d.type === "nombre" ? [`${d.champ}__gte`, `${d.champ}__lte`] : [d.champ];
  const actifsAutres =
    autres.reduce((n, d) => n + champsDe(d).filter((k) => (value[k] ?? "").trim()).length, 0) + moreKeys.filter((k) => (value[k] ?? "").trim()).length;

  const controle = (d: FilterDef, inline: boolean) => {
    const id = `${idPrefix}-${d.champ}`;
    const libelle = cleanFilterLabel(d.libelle);
    if (d.type === "date") {
      return (
        <DateRangePicker
          id={id}
          aria-label={libelle}
          placeholder={inline ? libelle : undefined}
          className="filter-control"
          months={inline ? 2 : 1}
          value={{ from: value[`${d.champ}__gte`] ?? "", to: value[`${d.champ}__lte`] ?? "" }}
          onChange={(r) => onChange({ ...value, [`${d.champ}__gte`]: r.from, [`${d.champ}__lte`]: r.to })}
        />
      );
    }
    if (d.type === "nombre") {
      return (
        <div className="filter-range" role="group" aria-label={libelle}>
          <input
            id={`${id}-du`}
            type="number"
            className="control"
            placeholder={t("formulaires.filtres.min")}
            aria-label={`${libelle} — ${t("ecarts_a1.filtres.du")}`}
            value={value[`${d.champ}__gte`] ?? ""}
            onChange={(e) => set(`${d.champ}__gte`, e.target.value)}
          />
          <input
            id={`${id}-au`}
            type="number"
            className="control"
            placeholder={t("formulaires.filtres.max")}
            aria-label={`${libelle} — ${t("ecarts_a1.filtres.au")}`}
            value={value[`${d.champ}__lte`] ?? ""}
            onChange={(e) => set(`${d.champ}__lte`, e.target.value)}
          />
        </div>
      );
    }
    const liste = listeDe(d);
    if (liste) {
      return (
        <select id={id} className="filter-control" value={value[d.champ] ?? ""} onChange={(e) => set(d.champ, e.target.value)}>
          <option value="">{inline ? t("formulaires.filtres.tousLibelle", { libelle }) : t("ecarts_a1.filtres.tous")}</option>
          {liste.map((o) => (
            <option key={o.valeur} value={o.valeur}>
              {o.libelle}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        id={id}
        className="filter-control"
        placeholder={inline ? libelle : undefined}
        value={value[d.champ] ?? ""}
        onChange={(e) => set(d.champ, e.target.value)}
      />
    );
  };

  return (
    <div className="filter-bar" role="group" aria-label={t("ecarts_a1.filtres.titre")}>
      {search ? <div className="filter-bar-search">{search}</div> : null}
      {enLigne.map((d) => (
        <div key={d.champ} className={`filter-bar-item filter-bar-item--${d.type}`}>
          {d.type === "date" || d.type === "nombre" ? null : (
            <label className="sr-only" htmlFor={`${idPrefix}-${d.champ}`}>
              {cleanFilterLabel(d.libelle)}
            </label>
          )}
          {controle(d, true)}
        </div>
      ))}
      {autres.length > 0 || more ? (
        <Popover
          label={t("formulaires.filtres.plus")}
          align="end"
          className="filter-more-pop"
          trigger={
            <button type="button" className={`btn ghost filter-more${actifsAutres ? " has-active" : ""}`}>
              <SlidersHorizontal size={15} aria-hidden="true" />
              {t("formulaires.filtres.plus")}
              {actifsAutres ? <span className="filter-count">{actifsAutres}</span> : null}
            </button>
          }
        >
          <div className="filter-more-grid">
            {autres.map((d) =>
              d.type === "date" || d.type === "nombre" ? (
                <div key={d.champ} className="field">
                  <span className="filter-more-label" id={`${idPrefix}-${d.champ}-l`}>
                    {cleanFilterLabel(d.libelle)}
                  </span>
                  {controle(d, false)}
                </div>
              ) : (
                <div key={d.champ} className="field">
                  <label htmlFor={`${idPrefix}-${d.champ}`}>{cleanFilterLabel(d.libelle)}</label>
                  {controle(d, false)}
                </div>
              ),
            )}
            {more}
          </div>
        </Popover>
      ) : null}
      {actifs > 0 && (
        <button
          type="button"
          className="btn ghost filter-clear"
          onClick={() => onChange({})}
        >
          <FilterX size={14} aria-hidden="true" /> {t("ecarts_a1.filtres.effacer", { count: actifs })}
        </button>
      )}
    </div>
  );
}
