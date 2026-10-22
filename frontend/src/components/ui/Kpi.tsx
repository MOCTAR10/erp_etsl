import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

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

/** Carte KPI standard — libellé, valeur (count-up si numérique), indication, icône en tonalité douce. */
export function Kpi({ label, value, hint, icon: Icon, tone = "brand", delay = 0, kind = "number", format }: Props) {
  const fmt = format ?? FORMATS[kind];
  let text: string;
  let display: ReactNode;
  if (typeof value === "number") {
    text = fmt(value);
    display = <AnimatedNumber value={value} format={fmt} />;
  } else {
    // Chaîne : montant API formaté si `kind="money"`, sinon telle quelle (« — » masqué inclus).
    text = kind === "money" ? formatMoney(value) : (value ?? "—");
    display = text;
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
      <span className={`kpi-value${sizeClass(text)}`}>{display}</span>
      {hint ? <span className="kpi-hint">{hint}</span> : null}
    </motion.div>
  );
}
