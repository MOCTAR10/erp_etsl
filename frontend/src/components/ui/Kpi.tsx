import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import type { CSSProperties, ReactNode } from "react";

import { formatMoney, formatNumber, formatPercent } from "../../lib/format";
import { motionTokens } from "../../theme/tokens";
import { AnimatedNumber } from "./AnimatedNumber";

type Tone = "brand" | "ok" | "warn" | "err" | "accent" | "neutral";

/** Nature de la valeur : nombre (défaut), montant FCFA exact (« 25 000 000 FCFA »), pourcentage. */
export type KpiKind = "number" | "money" | "percent";

type Props = {
  label: string;
  value: number | string | null | undefined;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: Tone;
  delay?: number;
  kind?: KpiKind;
  /** Format explicite (prioritaire sur `kind`) ; doit être une référence stable. */
  format?: (n: number) => string;
};

const money = (n: number) => formatMoney(n);
const UNIT = " FCFA";
/** Montant sans l'unité (« 25 000 000 ») — l'unité est rendue à part pour ne jamais être coupée. */
const moneyBody = (n: number) => {
  const text = formatMoney(n);
  return text.endsWith(UNIT) ? text.slice(0, -UNIT.length) : text;
};
const percent = (n: number) => formatPercent(n);
const FORMATS: Record<KpiKind, (n: number) => string> = {
  number: formatNumber,
  money,
  percent,
};

/**
 * Taille de la valeur selon sa longueur : un montant n'est jamais abrégé,
 * c'est la police qui se réduit (28 → 22 → 18 px) pour tenir dans la carte.
 */
function sizeClass(text: string): string {
  if (text.length > 16) return " kpi-value-sm";
  if (text.length > 11) return " kpi-value-md";
  return "";
}

/**
 * Largeur estimée d'un montant, en cadratins (Inter gras, chiffres tabulaires) : chiffre ≈ 0,62 em,
 * espace insécable ≈ 0,28 em, signe ≈ 0,45 em. Sert au calcul CSS de la taille qui tient dans la carte (B15).
 */
function moneyEm(body: string): number {
  let em = 0;
  for (const ch of body) {
    if (ch >= "0" && ch <= "9") em += 0.62;
    else if (ch === "-" || ch === "−" || ch === "+") em += 0.45;
    else if (ch.trim() === "") em += 0.28;
    else em += 0.6;
  }
  return Math.round(em * 100) / 100;
}

/** Carte KPI standard — libellé, valeur (count-up si numérique), indication, icône en tonalité douce. */
export function Kpi({ label, value, hint, icon: Icon, tone = "brand", delay = 0, kind = "number", format }: Props) {
  const fmt = format ?? FORMATS[kind];
  let text: string;
  let display: ReactNode;
  const moneyUnit = !format && kind === "money";
  if (typeof value === "number") {
    text = fmt(value);
    display = moneyUnit ? <AnimatedNumber value={value} format={moneyBody} /> : <AnimatedNumber value={value} format={fmt} />;
  } else {
    // Chaîne : montant API formaté si `kind="money"`, sinon telle quelle (« — » masqué inclus).
    text = kind === "money" ? formatMoney(value) : (value ?? "—");
    display = text;
  }
  // Montant : « 25 000 000 » et « FCFA » restent chacun d'un bloc ; sur une carte étroite, seule la coupure
  // entre le nombre et l'unité est permise (jamais au milieu de « FCFA »). Texte lu : « 25 000 000 FCFA ».
  // B15 : un montant garde la taille KPI (28 px) tant qu'il tient dans la carte ; sinon la police se réduit
  // juste assez (calcul CSS d'après sa largeur estimée), l'unité « FCFA » restant à 14 px.
  let valueClass = `kpi-value${sizeClass(text)}`;
  let valueStyle: CSSProperties | undefined;
  if (moneyUnit && text.endsWith(UNIT)) {
    valueClass = "kpi-value kpi-value-fit";
    valueStyle = { "--kpi-em": moneyEm(text.slice(0, -UNIT.length)) } as CSSProperties;
    const body = typeof value === "number" ? display : text.slice(0, -UNIT.length);
    display = (
      <>
        <span className="ui-kpi-num">{body}</span>
        {" "}
        <wbr />
        <span className="ui-kpi-unit">FCFA</span>
      </>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: motionTokens.distance.xs }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: motionTokens.duration.fast, ease: motionTokens.ease.out, delay }}
      className="card kpi"
    >
      <div className="kpi-head">
        <span className="kpi-label">{label}</span>
        {Icon ? (
          <span className={`kpi-icon ${tone}`} aria-hidden>
            <Icon size={16} strokeWidth={1.75} />
          </span>
        ) : null}
      </div>
      <span className={valueClass} style={valueStyle}>
        {display}
      </span>
      {hint ? <span className="kpi-hint">{hint}</span> : null}
    </motion.div>
  );
}
