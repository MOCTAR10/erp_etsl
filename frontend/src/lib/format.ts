import i18n from "i18next";

/**
 * Formats d'affichage uniques de l'ERP (montants, nombres, pourcentages, dates).
 * - Nombres et montants : convention française (« 25 000 000 FCFA », « 0,75 »),
 *   quelle que soit la langue de l'interface (usage gabonais du FCFA).
 * - Dates : suivent le sélecteur FR/EN.
 * - Valeur absente → « — » ; valeur masquée (`has_amount_access` = false côté
 *   serveur : « — », « •••••• ») → renvoyée telle quelle.
 * Les espaces insérés sont insécables (pas de retour à la ligne dans un montant).
 */

/** Langue active de l'interface (FR par défaut) : les dates suivent le sélecteur FR/EN. */
const currentLocale = () => i18n.language || "fr";

const NUMBER_LOCALE = "fr-FR";
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

export type NumberOptions = {
  /** Nombre de décimales fixes (défaut : 0). */
  decimals?: number;
};

/** « 1 234 567 » ; « 0,75 » avec `{ decimals: 2 }` ; « — » si absent ou non numérique. */
export function formatNumber(value: Numeric, options: NumberOptions = {}): string {
  const n = toNumber(value);
  if (n === null) return EMPTY;
  const decimals = options.decimals ?? 0;
  return n.toLocaleString(NUMBER_LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export type MoneyOptions = {
  /** Version compacte pour les KPI : « 25 M FCFA », « 1,2 Md FCFA » (à partir du million). */
  compact?: boolean;
  /** Libellé de devise (défaut « FCFA »). */
  currency?: string;
};

const compactFormatter = new Intl.NumberFormat(NUMBER_LOCALE, { notation: "compact" });

/**
 * Montant en FCFA : « 25 000 000 FCFA » ; compact : « 25 M FCFA ».
 * Une chaîne non numérique (montant masqué « — » / « •••••• ») est renvoyée telle quelle ;
 * `null` / `undefined` / « » → « — ».
 */
export function formatMoney(value: Numeric, options: MoneyOptions = {}): string {
  const n = toNumber(value);
  if (n === null) {
    return typeof value === "string" && value.trim() !== "" ? value : EMPTY;
  }
  const currency = options.currency ?? "FCFA";
  const body =
    options.compact && Math.abs(n) >= 1_000_000
      ? compactFormatter.format(n)
      : n.toLocaleString(NUMBER_LOCALE, { maximumFractionDigits: 0 });
  return `${body.replace(/ /g, NBSP)}${NBSP}${currency}`;
}

/** Variante compacte à référence stable (prop `format` de Kpi / AnimatedNumber). */
export const formatMoneyCompact = (value: Numeric): string => formatMoney(value, { compact: true });

export type PercentOptions = {
  /** Décimales (défaut 0). */
  decimals?: number;
  /** `true` si la valeur est un ratio (0,75 → « 75 % ») ; par défaut elle est déjà en points. */
  ratio?: boolean;
};

/** « 75 % » ; « 7,5 % » avec `{ decimals: 1 }` ; « — » si absent. */
export function formatPercent(value: Numeric, options: PercentOptions = {}): string {
  const n = toNumber(value);
  if (n === null) return EMPTY;
  const pct = options.ratio ? n * 100 : n;
  return `${formatNumber(pct, { decimals: options.decimals ?? 0 })}${NBSP}%`;
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
  return d.toLocaleDateString(currentLocale().startsWith("en") ? "en-GB" : "fr-FR", {
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
