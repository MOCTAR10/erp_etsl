import * as RadixPopover from "@radix-ui/react-popover";
import { CalendarDays, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { DayPicker } from "react-day-picker";
import type { DateRange, Matcher } from "react-day-picker";
import { enGB, fr } from "react-day-picker/locale";
import "react-day-picker/style.css";
import { useTranslation } from "react-i18next";

/*
 * Sélecteurs de date (react-day-picker v10) : affichage jj/mm/aaaa (FR comme EN), valeur ISO « AAAA-MM-JJ »
 * en entrée / sortie (format DRF des DateField), chaîne vide = pas de date. Calendrier en français ou en
 * anglais selon i18n, semaine commençant le lundi. Compatibles avec `.field` (`<label htmlFor={id}>`)
 * et avec les formulaires non contrôlés lus par `FormData` (`name` → champ caché ISO).
 */

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** « 2026-10-22 » → Date locale (minuit) ; `undefined` si vide ou invalide. */
export function isoToDate(iso?: string | null): Date | undefined {
  const m = iso ? ISO_RE.exec(iso) : null;
  if (!m) return undefined;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.getMonth() === Number(m[2]) - 1 && d.getDate() === Number(m[3]) ? d : undefined;
}

/** Date locale → « AAAA-MM-JJ » (sans passer par UTC : pas de décalage de fuseau). */
export function dateToIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** « 2026-10-22 » → « 22/10/2026 » (chaîne vide si pas de date). */
export function formatIsoDate(iso?: string | null): string {
  const d = isoToDate(iso);
  if (!d) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

/**
 * Saisie libre → ISO : « 22/10/2026 », « 22-10-2026 », « 22.10.2026 », « 22102026 », « 2/1/26 » (→ 2026),
 * ou déjà ISO. `""` si vide, `null` si illisible.
 */
export function parseDateInput(text: string): string | null {
  const s = text.trim();
  if (!s) return "";
  if (ISO_RE.test(s)) return isoToDate(s) ? s : null;
  let m = /^(\d{1,2})[/.\-\s](\d{1,2})[/.\-\s](\d{2}|\d{4})$/.exec(s);
  if (!m && /^\d{8}$/.test(s)) m = /^(\d{2})(\d{2})(\d{4})$/.exec(s);
  if (!m) return null;
  const year = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
  const iso = `${year}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
  return isoToDate(iso) ? iso : null;
}

function useCalendarLocale() {
  const { i18n } = useTranslation();
  return (i18n.resolvedLanguage ?? i18n.language ?? "fr").startsWith("en") ? enGB : fr;
}

function bounds(min?: string, max?: string) {
  const lo = isoToDate(min);
  const hi = isoToDate(max);
  const disabled: Matcher[] = [];
  if (lo) disabled.push({ before: lo });
  if (hi) disabled.push({ after: hi });
  return { lo, hi, disabled };
}

function inBounds(iso: string, min?: string, max?: string) {
  return !iso || ((!min || iso >= min) && (!max || iso <= max));
}

/** État contrôlé (`value`) ou interne (`defaultValue`). */
function useValue<T>(value: T | undefined, defaultValue: T, onChange?: (v: T) => void) {
  const [inner, setInner] = useState(defaultValue);
  const current = value !== undefined ? value : inner;
  const set = (v: T) => {
    if (value === undefined) setInner(v);
    onChange?.(v);
  };
  return [current, set] as const;
}

export interface DatePickerProps {
  id?: string;
  /** Nom du champ caché (valeur ISO) pour les formulaires lus par `FormData`. */
  name?: string;
  /** Valeur contrôlée ISO (`""` = vide). */
  value?: string;
  defaultValue?: string;
  onChange?: (iso: string) => void;
  /** Bornes ISO incluses. */
  min?: string;
  max?: string;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  /** Nom accessible quand aucun `<label htmlFor>` n'est associé. */
  "aria-label"?: string;
  "aria-describedby"?: string;
  /** Menus mois / année dans l'en-tête du calendrier (dates de naissance, échéances lointaines). */
  dropdowns?: boolean;
  className?: string;
}

/**
 * Champ date : saisie clavier jj/mm/aaaa (validée à la sortie du champ) + calendrier en fenêtre flottante
 * (bouton icône, ou Alt+↓ dans le champ). `<div className="field"><label htmlFor="d">Date</label><DatePicker id="d" name="document_date" /></div>`.
 */
export function DatePicker({
  id,
  name,
  value,
  defaultValue = "",
  onChange,
  min,
  max,
  required,
  disabled,
  placeholder,
  dropdowns,
  className,
  ...aria
}: DatePickerProps) {
  const { t } = useTranslation();
  const locale = useCalendarLocale();
  const errId = useId();
  const [iso, setIso] = useValue(value, defaultValue, onChange);
  const [text, setText] = useState(() => formatIsoDate(iso));
  const [invalid, setInvalid] = useState(false);
  const [open, setOpen] = useState(false);
  const { lo, hi, disabled: outOfRange } = bounds(min, max);

  // Valeur modifiée de l'extérieur (ou par le calendrier) : le texte affiché suit.
  useEffect(() => {
    setText(formatIsoDate(iso));
    setInvalid(false);
  }, [iso]);

  const commitText = () => {
    const parsed = parseDateInput(text);
    if (parsed === null || !inBounds(parsed, min, max)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    if (parsed !== iso) setIso(parsed);
    else setText(formatIsoDate(parsed));
  };

  const selected = isoToDate(iso);
  return (
    <RadixPopover.Root open={open} onOpenChange={setOpen}>
      <div className={`ui-date${invalid ? " is-invalid" : ""}${disabled ? " is-disabled" : ""} ${className ?? ""}`.trim()}>
        <RadixPopover.Anchor asChild>
          <div className="ui-date-control">
          <input
            id={id}
            type="text"
            inputMode="numeric"
            autoComplete="off"
            className="ui-date-input"
            value={text}
            placeholder={placeholder ?? t("ui.date.placeholder")}
            disabled={disabled}
            required={required}
            aria-invalid={invalid || undefined}
            aria-describedby={[aria["aria-describedby"], invalid ? errId : undefined].filter(Boolean).join(" ") || undefined}
            aria-label={aria["aria-label"]}
            onChange={(e) => setText(e.target.value)}
            onBlur={commitText}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitText();
              if (e.key === "ArrowDown" && e.altKey) {
                e.preventDefault();
                setOpen(true);
              }
            }}
          />
          <RadixPopover.Trigger asChild>
            <button type="button" className="ui-date-btn" aria-label={t("ui.date.openCalendar")} disabled={disabled}>
              <CalendarDays size={16} aria-hidden />
            </button>
          </RadixPopover.Trigger>
          </div>
        </RadixPopover.Anchor>
        {name ? <input type="hidden" name={name} value={iso} /> : null}
        {invalid ? (
          <span id={errId} className="ui-field-error" role="alert">
            {t("ui.date.invalid")}
          </span>
        ) : null}
      </div>
      <RadixPopover.Portal>
        <RadixPopover.Content className="ui-popover ui-pop ui-calendar-pop" align="start" sideOffset={6} collisionPadding={12}>
          <DayPicker
            mode="single"
            locale={locale}
            weekStartsOn={1}
            showOutsideDays
            autoFocus
            captionLayout={dropdowns ? "dropdown" : "label"}
            selected={selected}
            defaultMonth={selected ?? lo ?? undefined}
            startMonth={lo ?? (dropdowns ? new Date(1950, 0) : undefined)}
            endMonth={hi ?? (dropdowns ? new Date(new Date().getFullYear() + 15, 11) : undefined)}
            disabled={outOfRange}
            className="ui-calendar"
            onSelect={(d) => {
              // re-clic sur le jour choisi : on garde la date (l'effacement passe par « Effacer »)
              if (d) setIso(dateToIso(d));
              setOpen(false);
            }}
          />
          <div className="ui-calendar-foot">
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => {
                const today = dateToIso(new Date());
                if (inBounds(today, min, max)) setIso(today);
                setOpen(false);
              }}
            >
              {t("ui.date.today")}
            </button>
            {iso && !required ? (
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  setIso("");
                  setOpen(false);
                }}
              >
                <X size={13} aria-hidden />
                {t("ui.date.clear")}
              </button>
            ) : null}
          </div>
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}

export interface DateRangeValue {
  /** ISO « AAAA-MM-JJ » ou `""`. */
  from: string;
  to: string;
}

export interface DateRangePickerProps {
  id?: string;
  /** Noms des champs cachés ISO (formulaires `FormData`), ex. `date_min` / `date_max`. */
  nameFrom?: string;
  nameTo?: string;
  value?: DateRangeValue;
  defaultValue?: DateRangeValue;
  onChange?: (range: DateRangeValue) => void;
  min?: string;
  max?: string;
  disabled?: boolean;
  placeholder?: string;
  "aria-label"?: string;
  /** Nombre de mois affichés (défaut 2 ; 1 sur mobile via CSS si l'espace manque). */
  months?: number;
  className?: string;
}

const EMPTY_RANGE: DateRangeValue = { from: "", to: "" };

/**
 * Période (du … au …) : bouton-champ + calendrier double ; le panneau se ferme au 2e clic (fin de période).
 * `<DateRangePicker id="periode" value={p} onChange={setP} />` — `p = { from: "2026-10-01", to: "2026-10-31" }`.
 */
export function DateRangePicker({
  id,
  nameFrom,
  nameTo,
  value,
  defaultValue = EMPTY_RANGE,
  onChange,
  min,
  max,
  disabled,
  placeholder,
  months = 2,
  className,
  ...aria
}: DateRangePickerProps) {
  const { t } = useTranslation();
  const locale = useCalendarLocale();
  const valueId = useId();
  const [range, setRange] = useValue(value, defaultValue, onChange);
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const { lo, hi, disabled: outOfRange } = bounds(min, max);
  const selected: DateRange | undefined = range.from ? { from: isoToDate(range.from), to: isoToDate(range.to) } : undefined;
  const label = range.from
    ? `${formatIsoDate(range.from)} – ${range.to ? formatIsoDate(range.to) : "…"}`
    : (placeholder ?? t("ui.date.rangePlaceholder"));

  return (
    <RadixPopover.Root
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        setPicking(false);
      }}
    >
      <RadixPopover.Trigger asChild>
        <button
          id={id}
          type="button"
          className={`ui-date-trigger${range.from ? "" : " is-empty"} ${className ?? ""}`.trim()}
          disabled={disabled}
          aria-label={aria["aria-label"]}
          aria-describedby={valueId}
        >
          <span id={valueId}>{label}</span>
          <CalendarDays size={16} aria-hidden />
        </button>
      </RadixPopover.Trigger>
      {nameFrom ? <input type="hidden" name={nameFrom} value={range.from} /> : null}
      {nameTo ? <input type="hidden" name={nameTo} value={range.to} /> : null}
      <RadixPopover.Portal>
        <RadixPopover.Content className="ui-popover ui-pop ui-calendar-pop" align="start" sideOffset={6} collisionPadding={12}>
          <DayPicker
            mode="range"
            locale={locale}
            weekStartsOn={1}
            numberOfMonths={months}
            showOutsideDays
            autoFocus
            selected={selected}
            defaultMonth={selected?.from ?? lo ?? undefined}
            startMonth={lo}
            endMonth={hi}
            disabled={outOfRange}
            className="ui-calendar"
            onSelect={(r) => {
              setRange({ from: r?.from ? dateToIso(r.from) : "", to: r?.to ? dateToIso(r.to) : "" });
              if (picking) {
                setOpen(false);
                setPicking(false);
              } else {
                setPicking(true);
              }
            }}
          />
          <div className="ui-calendar-foot">
            {range.from ? (
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  setRange(EMPTY_RANGE);
                  setPicking(false);
                }}
              >
                <X size={13} aria-hidden />
                {t("ui.date.clear")}
              </button>
            ) : null}
          </div>
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
