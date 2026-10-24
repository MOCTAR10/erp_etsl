import { useTranslation } from "react-i18next";

/*
 * Sélecteur de mois : remplace `<input type="month">`, dont le rendu suit la langue du NAVIGATEUR
 * (« October 2026 » dans une interface française) et qui s'affiche vide (« --------- ---- ») sous Firefox.
 * Liste déroulante du kit (`select.control`) de mois libellés dans la langue de l'interface
 * (« Octobre 2026 » / « October 2026 »), valeur « AAAA-MM » en entrée / sortie (format des API mensuelles),
 * chaîne vide = aucun mois. Compatible `.field` (`<label htmlFor={id}>`) et `FormData` (`name`).
 */

const MONTH_RE = /^(\d{4})-(\d{1,2})$/;

/** « 2026-10 » (ou « 2026-10-01 ») → « 2026-10 » normalisé ; `""` si illisible. */
export function normalizeMonth(value?: string | null): string {
  const m = value ? MONTH_RE.exec(value.slice(0, 7)) ?? MONTH_RE.exec(value) : null;
  if (!m) return "";
  const month = Number(m[2]);
  if (month < 1 || month > 12) return "";
  return `${m[1]}-${String(month).padStart(2, "0")}`;
}

/** Mois courant « AAAA-MM » (heure locale). */
export function currentMonth(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Décale un mois « AAAA-MM » de `delta` mois. */
export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return currentMonth(d);
}

/** « 2026-10 » → « Octobre 2026 » (FR) / « October 2026 » (EN), première lettre en capitale. */
export function formatMonth(month: string, locale: string): string {
  const norm = normalizeMonth(month);
  if (!norm) return "";
  const [y, m] = norm.split("-").map(Number);
  const label = new Date(y, m - 1, 1).toLocaleDateString(locale.startsWith("en") ? "en-GB" : "fr-FR", { month: "long", year: "numeric" });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** Mois proposés, du plus récent au plus ancien, entre `min` et `max` (bornes incluses). */
export function monthRange(min: string, max: string): string[] {
  const out: string[] = [];
  let cur = max;
  for (let i = 0; i < 240 && cur >= min; i += 1) {
    out.push(cur);
    cur = shiftMonth(cur, -1);
  }
  return out;
}

export interface MonthPickerProps {
  id?: string;
  name?: string;
  /** Mois « AAAA-MM » ; `""` = aucun. */
  value: string;
  onChange: (value: string) => void;
  /** Premier mois proposé (défaut : 24 mois avant le mois courant). */
  min?: string;
  /** Dernier mois proposé (défaut : 12 mois après le mois courant). */
  max?: string;
  /** Option vide en tête (« Tous les mois », « — »…) ; absente si non fournie. */
  emptyLabel?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}

/** `<MonthPicker id="mois" value={mois} onChange={setMois} />` dans un `.field` avec son `<label htmlFor>`. */
export function MonthPicker({ id, name, value, onChange, min, max, emptyLabel, required, disabled, className, ...rest }: MonthPickerProps) {
  const { i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language ?? "fr";
  const now = currentMonth();
  const hi = normalizeMonth(max) || shiftMonth(now, 12);
  const lo = normalizeMonth(min) || shiftMonth(now, -24);
  const months = monthRange(lo, hi);
  const current = normalizeMonth(value);
  // Une valeur hors plage reste sélectionnable (jamais de valeur silencieusement perdue).
  if (current && !months.includes(current)) {
    months.push(current);
    months.sort((a, b) => (a < b ? 1 : -1));
  }
  return (
    <select
      id={id}
      name={name}
      className={["control", "month-picker", className].filter(Boolean).join(" ")}
      value={current}
      required={required}
      disabled={disabled}
      aria-label={rest["aria-label"]}
      onChange={(e) => onChange(e.target.value)}
    >
      {emptyLabel !== undefined || !current ? <option value="">{emptyLabel ?? "—"}</option> : null}
      {months.map((m) => (
        <option key={m} value={m}>
          {formatMonth(m, locale)}
        </option>
      ))}
    </select>
  );
}
