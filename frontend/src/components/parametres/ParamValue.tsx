import { useState } from "react";
import { useTranslation } from "react-i18next";

import { formatMoney, formatNumber, formatParametre, formatPercent } from "../../lib/format";
import { libelleCourt, optionPourValeur, uniteCle, UNITES_BOOLEENNES, UNITES_CODEES, UNITES_TECHNIQUES, type ParametreEtsl } from "../../lib/parametres";
import { roleLabel } from "../../lib/roles";

type T = ReturnType<typeof useTranslation>["t"];
/** Au-delà, une liste JSON est repliée derrière « Voir tout ». */
const PLI = 3;

const majuscule = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/** Code de rôle (« secretaire_general ») → libellé ; tout autre texte reste tel quel. */
function texteLisible(t: T, i18nExists: (k: string) => boolean, s: string): string {
  return i18nExists(`shell.roles.${s}`) ? roleLabel(t, s) : s;
}

/** Clé d'objet JSON lisible : rôle traduit, sinon « separateur_decimal » → « Separateur decimal ». */
function cleLisible(t: T, i18nExists: (k: string) => boolean, k: string): string {
  if (i18nExists(`shell.roles.${k}`)) return roleLabel(t, k);
  if (k === "_defaut") return t("premiumParams.valeur.defaut");
  return majuscule(k.replace(/_/g, " "));
}

/**
 * Valeur scalaire d'un paramètre en texte lisible (A-12) : option d'un choix codé, Oui / Non, compte sans
 * séparateur (« 624000 »), montants exacts en FCFA, unité technique (score, choix, rôles…) jamais affichée.
 */
export function valeurScalaire(t: T, i18nExists: (k: string) => boolean, p: Pick<ParametreEtsl, "valeur" | "unite" | "label" | "type_valeur">): string {
  const v = (p.valeur ?? "").trim();
  if (!v) return "—";
  const u = uniteCle(p.unite);
  if (u === "rôles" || u === "roles") return v.split(/\s*,\s*/).filter(Boolean).map((r) => roleLabel(t, r)).join(", ");
  if (p.type_valeur === "texte") return v;
  if (UNITES_BOOLEENNES.has(u)) {
    return optionPourValeur(p.label, v) ?? (Number(v) ? t("premiumParams.valeur.oui") : t("premiumParams.valeur.non"));
  }
  if (UNITES_CODEES.has(u)) {
    const n = Number(v);
    return optionPourValeur(p.label, v) ?? (Number.isFinite(n) ? String(Math.trunc(n)) : v);
  }
  if (UNITES_TECHNIQUES.has(u)) {
    const n = Number(v);
    return Number.isFinite(n) ? formatNumber(n, { decimals: Number.isInteger(n) ? 0 : 2 }) : v;
  }
  return formatParametre(v, p.unite);
}

/** Élément d'une valeur JSON en texte : nombres formatés (FCFA / % selon le libellé), rôles traduits, listes jointes. */
function elementJson(t: T, i18nExists: (k: string) => boolean, x: unknown, sens: "fcfa" | "pct" | ""): string {
  if (x === null || x === undefined) return "—";
  if (typeof x === "boolean") return x ? t("premiumParams.valeur.oui") : t("premiumParams.valeur.non");
  if (typeof x === "number") return sens === "fcfa" ? formatMoney(x) : sens === "pct" ? formatPercent(x, { decimals: Number.isInteger(x) ? 0 : 1 }) : formatNumber(x, { decimals: Number.isInteger(x) ? 0 : 2 });
  if (typeof x === "string") return texteLisible(t, i18nExists, x);
  if (Array.isArray(x)) return x.map((y) => elementJson(t, i18nExists, y, sens)).join(", ");
  return Object.entries(x as Record<string, unknown>)
    .map(([k, y]) => `${cleLisible(t, i18nExists, k)} : ${elementJson(t, i18nExists, y, sens)}`)
    .join(" ; ");
}

/** Valeur JSON rendue en puces (liste) ou en paires « clé : valeur » (objet), repliée au-delà de 3 lignes (A-06). */
function ValeurJson({ p }: { p: Pick<ParametreEtsl, "valeur" | "label" | "unite"> }) {
  const { t, i18n } = useTranslation();
  const [tout, setTout] = useState(false);
  const exists = (k: string) => i18n.exists(k);
  let v: unknown;
  try {
    v = JSON.parse(p.valeur);
  } catch {
    return <span>{p.valeur || "—"}</span>;
  }
  const sens: "fcfa" | "pct" | "" = /FCFA/i.test(`${p.label} ${p.unite}`) ? "fcfa" : /\(%\)|en %|%\)/.test(p.label) ? "pct" : "";
  if (v === null || typeof v !== "object") return <span className="num">{elementJson(t, exists, v, sens)}</span>;
  // Liste courte de nombres (paliers « 90, 60, 30, 15, 0 ») : une ligne suffit.
  if (Array.isArray(v) && v.every((x) => typeof x === "number")) return <span className="num">{elementJson(t, exists, v, sens)}</span>;
  const lignes: { cle?: string; valeur: string }[] = Array.isArray(v)
    ? v.map((x) => ({ valeur: elementJson(t, exists, x, sens) }))
    : Object.entries(v as Record<string, unknown>).map(([k, x]) => ({ cle: cleLisible(t, exists, k), valeur: elementJson(t, exists, x, sens) }));
  if (lignes.length === 0) return <span>—</span>;
  const visibles = tout ? lignes : lignes.slice(0, PLI);
  return (
    <div className="param-json-view">
      <ul className={Array.isArray(v) ? "param-json-list" : "param-json-pairs"}>
        {visibles.map((l, i) => (
          <li key={`${l.cle ?? ""}-${i}`}>
            {l.cle ? <span className="param-json-key">{l.cle}</span> : null}
            <span className="param-json-val">{l.valeur}</span>
          </li>
        ))}
      </ul>
      {lignes.length > PLI ? (
        <button type="button" className="param-json-more" aria-expanded={tout} onClick={() => setTout((x) => !x)}>
          {tout ? t("premiumParams.valeur.voirMoins") : t("premiumParams.valeur.voirTout", { count: lignes.length })}
        </button>
      ) : null}
    </div>
  );
}

/** Valeur d'un paramètre du registre central, lisible quel que soit son type (motif de ligne partagé, A-36). */
export function ParamValue({ p }: { p: ParametreEtsl }) {
  const { t, i18n } = useTranslation();
  if (p.type_valeur === "json") return <ValeurJson p={p} />;
  const texte = valeurScalaire(t, (k) => i18n.exists(k), p);
  return <span className={p.type_valeur === "texte" ? "param-value-text" : "num cell-nowrap"}>{texte}</span>;
}

/** Cible d'un KPI de contrôle de gestion (`KPI_01`) : libellé de l'indicateur plutôt que « Cible du KPI KP-M11-01 » (B-06). */
export const estCibleKpi = (code: string) => /^KPI_\d{2}$/.test(code);
/** « KPI_04 » → « KP-M11-04 » (référence du CDC, affichée en secondaire). */
export const referenceKpi = (code: string) => (estCibleKpi(code) ? `KP-M11-${code.slice(4)}` : undefined);

/**
 * Libellé humain d'un paramètre (B-06 / B-14) : traduction connue (cibles KPI, paie), sinon libellé du serveur sans
 * la liste des options codées (affichée par la valeur).
 */
export function libelleParametre(t: T, p: { code: string; label: string; module?: string }): string {
  if (estCibleKpi(p.code) && (!p.module || p.module === "controle_gestion")) return t(`premiumParams.kpiCibles.${p.code}`, { defaultValue: libelleCourt(p.label) });
  if (p.module === "rh_paie") return t(`premiumParams.paie.${p.code}`, { defaultValue: libelleCourt(p.label) });
  return libelleCourt(p.label);
}
