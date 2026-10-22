import { FilterX } from "lucide-react";
import { useTranslation } from "react-i18next";

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

/**
 * Barre de filtres multicritères réutilisable (EX-G-09) : un contrôle par critère, combinés en ET.
 * choix / fk → liste ; date / nombre → bornes « du … au … » ; bool → oui / non ; texte → contient.
 * `options` fournit la liste des valeurs d'une clé étrangère (ex. types de document chargés par la page).
 */
export function FilterBar({
  defs,
  value,
  onChange,
  options = {},
  idPrefix = "filtre",
}: {
  defs: FilterDef[];
  value: FilterValues;
  onChange: (next: FilterValues) => void;
  options?: Record<string, { valeur: string; libelle: string }[]>;
  idPrefix?: string;
}) {
  const { t } = useTranslation();
  const set = (k: string, v: string) => onChange({ ...value, [k]: v });
  const actifs = Object.values(value).filter((v) => v.trim()).length;

  return (
    <div className="filter-bar" role="group" aria-label={t("ecarts_a1.filtres.titre")}>
      <div className="quick-form-grid">
        {defs.map((d) => {
          const id = `${idPrefix}-${d.champ}`;
          if (d.type === "date" || d.type === "nombre") {
            const type = d.type === "date" ? "date" : "number";
            return (
              <fieldset key={d.champ} className="field filter-range">
                <legend>{d.libelle}</legend>
                <input
                  id={`${id}-du`}
                  type={type}
                  aria-label={`${d.libelle} — ${t("ecarts_a1.filtres.du")}`}
                  value={value[`${d.champ}__gte`] ?? ""}
                  onChange={(e) => set(`${d.champ}__gte`, e.target.value)}
                />
                <input
                  id={`${id}-au`}
                  type={type}
                  aria-label={`${d.libelle} — ${t("ecarts_a1.filtres.au")}`}
                  value={value[`${d.champ}__lte`] ?? ""}
                  onChange={(e) => set(`${d.champ}__lte`, e.target.value)}
                />
              </fieldset>
            );
          }
          const liste =
            d.type === "choix"
              ? (d.choix ?? [])
              : d.type === "fk"
                ? (options[d.champ] ?? null)
                : d.type === "bool"
                  ? [
                      { valeur: "true", libelle: t("ecarts_a1.filtres.oui") },
                      { valeur: "false", libelle: t("ecarts_a1.filtres.non") },
                    ]
                  : null;
          if (d.type === "fk" && !liste) return null; // pas de valeurs fournies : critère masqué
          return (
            <div key={d.champ} className="field">
              <label htmlFor={id}>{d.libelle}</label>
              {liste ? (
                <select id={id} value={value[d.champ] ?? ""} onChange={(e) => set(d.champ, e.target.value)}>
                  <option value="">{t("ecarts_a1.filtres.tous")}</option>
                  {liste.map((o) => (
                    <option key={o.valeur} value={o.valeur}>
                      {o.libelle}
                    </option>
                  ))}
                </select>
              ) : (
                <input id={id} value={value[d.champ] ?? ""} onChange={(e) => set(d.champ, e.target.value)} />
              )}
            </div>
          );
        })}
      </div>
      {actifs > 0 && (
        <button type="button" className="btn ghost" onClick={() => onChange({})}>
          <FilterX size={14} aria-hidden="true" /> {t("ecarts_a1.filtres.effacer", { count: actifs })}
        </button>
      )}
    </div>
  );
}
