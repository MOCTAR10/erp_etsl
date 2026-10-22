import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { formatMoney, formatMoneyCompact, formatNumber, formatPercent } from "../../lib/format";
import { motionTokens } from "../../theme/tokens";
import { AnimatedNumber } from "./AnimatedNumber";

type Tone = "brand" | "ok" | "warn" | "err" | "accent" | "neutral";

/** Nature de la valeur : nombre (défaut), montant FCFA (compact + montant exact en infobulle), pourcentage. */
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

const percent = (n: number) => formatPercent(n);
const FORMATS: Record<KpiKind, (n: number) => string> = {
  number: formatNumber,
  money: formatMoneyCompact,
  percent,
};

/** Carte KPI standard — libellé, valeur (count-up si numérique), indication, icône en tonalité douce. */
export function Kpi({ label, value, hint, icon: Icon, tone = "brand", delay = 0, kind = "number", format }: Props) {
  const fmt = format ?? FORMATS[kind];
  // Montant : valeur compacte affichée, montant exact en infobulle ; valeur masquée (« — ») inchangée.
  const exact = kind === "money" && value !== null && value !== undefined ? formatMoney(value) : undefined;
  let display: ReactNode;
  if (typeof value === "number") display = <AnimatedNumber value={value} format={fmt} />;
  else if (kind === "money") display = formatMoneyCompact(value);
  else display = value ?? "—";

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
      <span className="kpi-value" title={exact}>
        {display}
      </span>
      {hint ? <span className="kpi-hint">{hint}</span> : null}
    </motion.div>
  );
}
