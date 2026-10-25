import i18n from "i18next";

/**
 * Formats d'affichage uniques de l'ERP (montants, nombres, pourcentages, dates).
 * - Nombres et montants : suivent le sélecteur FR/EN — français « 25 000 000 FCFA », « 0,75 »,
 *   « 81,3 % » ; anglais « 25,000,000 FCFA », « 0.75 », « 81.3% ». La devise reste « FCFA »
 *   et le montant reste exact dans les deux langues.
 * - Dates : suivent le sélecteur FR/EN.
 * - Valeur absente → « — » ; valeur masquée (`has_amount_access` = false côté
 *   serveur : « — », « •••••• ») → renvoyée telle quelle.
 * Les espaces insérés sont insécables (pas de retour à la ligne dans un montant).
 */

/** Langue active de l'interface (FR par défaut) : les dates suivent le sélecteur FR/EN. */
const currentLocale = () => i18n.language || "fr";

/** Locale des nombres : `en-US` si l'interface est en anglais, sinon `fr-FR` (défaut). */
const isEnglish = () => currentLocale().startsWith("en");
const numberLocale = () => (isEnglish() ? "en-US" : "fr-FR");
const NBSP = " ";
export const EMPTY = "—";

type Numeric = string | number | null | undefined;

/** Convertit une valeur API (nombre ou chaîne décimale DRF) ; `null` si absente / non numérique. */
function toNumber(value: Numeric): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const v = bytes / 1024 ** i;
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

/**
 * Séparateur de milliers UNIQUE (A-14) : `fr-FR` produit une espace fine insécable (U+202F) pour les nombres,
 * les montants une espace insécable (U+00A0) — deux espacements côte à côte. Tout passe en U+00A0.
 */
const thousandsOnly = (text: string) => text.replace(/[  ]/g, NBSP);

/** Signe moins typographique U+2212 (« −818 000 FCFA ») : le trait d'union ASCII est trop court et s'écarte du chiffre. */
const MINUS = "−";
const minus = (text: string) => (/^-0([.,]0+)?$/.test(text) ? text.slice(1) : text.replace(/^-/, MINUS));
const thousands = (text: string) => minus(thousandsOnly(text));

export type NumberOptions = {
  /** Nombre de décimales fixes (défaut : 0). */
  decimals?: number;
};

/** « 1 234 567 » ; « 0,75 » avec `{ decimals: 2 }` ; « — » si absent ou non numérique. */
export function formatNumber(value: Numeric, options: NumberOptions = {}): string {
  const n = toNumber(value);
  if (n === null) return EMPTY;
  const decimals = options.decimals ?? 0;
  return thousands(
    n.toLocaleString(numberLocale(), {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }),
  );
}

export type MoneyOptions = {
  /** Libellé de devise (défaut « FCFA »). */
  currency?: string;
};

/**
 * Montant en FCFA, TOUJOURS exact et complet : « 25 000 000 FCFA » (séparateur de
 * milliers = espace insécable). Jamais d'abréviation (« 25 M ») — décision ETSL,
 * y compris dans les KPI : c'est la taille de police qui s'adapte, pas le nombre.
 * Une chaîne non numérique (montant masqué « — » / « •••••• ») est renvoyée telle quelle ;
 * `null` / `undefined` / « » → « — ».
 */
export function formatMoney(value: Numeric, options: MoneyOptions = {}): string {
  const n = toNumber(value);
  if (n === null) {
    return typeof value === "string" && value.trim() !== "" ? value : EMPTY;
  }
  const currency = options.currency ?? "FCFA";
  const body = n.toLocaleString(numberLocale(), { maximumFractionDigits: 0 });
  return `${thousands(body)}${NBSP}${currency}`;
}

export type PercentOptions = {
  /** Décimales (défaut 0). */
  decimals?: number;
  /** `true` si la valeur est un ratio (0,75 → « 75 % ») ; par défaut elle est déjà en points. */
  ratio?: boolean;
};

/** « 75 % » ; « 7,5 % » avec `{ decimals: 1 }` (EN : « 75% », « 7.5% ») ; « — » si absent. */
export function formatPercent(value: Numeric, options: PercentOptions = {}): string {
  const n = toNumber(value);
  if (n === null) return EMPTY;
  const pct = options.ratio ? n * 100 : n;
  return `${formatNumber(pct, { decimals: options.decimals ?? 0 })}${isEnglish() ? "" : NBSP}%`;
}

function toDate(iso: string | Date | null | undefined): Date | null {
  if (iso === null || iso === undefined || iso === "") return null;
  const d = iso instanceof Date ? iso : new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** « 23 sept. 2026 » (FR) / « Sep 23, 2026 » (EN) ; « — » si absente ou invalide. */
export function formatDate(iso: string | Date | null | undefined, locale: string = currentLocale()): string {
  const d = toDate(iso);
  if (!d) return EMPTY;
  return d.toLocaleDateString(locale, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Date numérique courte « 23/09/2026 » (FR et EN, ordre jour/mois/année) ; « — » si absente. */
export function formatDateShort(iso: string | Date | null | undefined): string {
  const d = toDate(iso);
  if (!d) return EMPTY;
  return d.toLocaleDateString(isEnglish() ? "en-GB" : "fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatDateTime(iso: string | Date | null | undefined, locale: string = currentLocale()): string {
  const d = toDate(iso);
  if (!d) return EMPTY;
  return d.toLocaleString(locale, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Unités de paramètres traduites (clé `revueKit.unites.<clé>`, pluriel i18next) ; les autres restent telles quelles. */
const UNITES: Record<string, string> = {
  jour: "jours",
  jours: "jours",
  j: "jours",
  heure: "heures",
  heures: "heures",
  h: "heures",
  mois: "mois",
  an: "ans",
  ans: "ans",
  "cycles/an": "cyclesAn",
  "cycle/an": "cyclesAn",
  semaine: "semaines",
  semaines: "semaines",
  minutes: "minutes",
  km: "km",
};

/**
 * Valeur d'un paramètre ETSL servie par l'API (`valeur` décimale DRF + `unite`) → texte lisible :
 * « 30 jours », « 50 000 000 FCFA », « 15 000 FCFA/h », « 90 % », « Oui » (unité 0/1),
 * « 411700 » (compte comptable : ni décimales ni séparateur ni unité), « 2,5 heures ».
 * Jamais « 30.00 jours », « 1.00 0/1 » ni « 411700.00 compte ».
 */
export function formatParametre(valeur: Numeric, unite?: string | null): string {
  const u = (unite ?? "").trim();
  const key = u.replace(/\s/g, "").toLowerCase();
  const n = toNumber(valeur);
  if (n === null) return typeof valeur === "string" && valeur.trim() !== "" ? valeur : EMPTY;
  if (key === "0/1" || key === "booleen" || key === "bool") return i18n.t(n ? "revueKit.oui" : "revueKit.non");
  if (key === "compte" || key === "code") return String(Math.trunc(n));
  const decimals = Number.isInteger(n) ? 0 : Math.abs(n * 10 - Math.round(n * 10)) < 1e-9 ? 1 : 2;
  if (key === "fcfa") return formatMoney(n);
  if (key.startsWith("fcfa/")) return formatMoney(n, { currency: `FCFA/${u.split("/").slice(1).join("/").trim()}` });
  if (key === "%") return formatPercent(n, { decimals });
  const num = formatNumber(n, { decimals });
  if (!u) return num;
  const k = UNITES[key];
  const label = k ? i18n.t(`revueKit.unites.${k}`, { count: n, defaultValue: u }) : u;
  return `${num}${NBSP}${label}`;
}
