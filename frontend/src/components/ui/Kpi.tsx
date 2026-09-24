import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { formatNumber } from "../../lib/format";
import { motionTokens } from "../../theme/tokens";
import { AnimatedNumber } from "./AnimatedNumber";

type Tone = "brand" | "ok" | "warn" | "err" | "accent" | "neutral";

type Props = {
  label: string;
  value: number | string | null | undefined;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: Tone;
  delay?: number;
  format?: (n: number) => string;
};

/** Carte KPI standard — valeur éventuellement animée (count-up), icône, ton. */
export function Kpi({
  label,
  value,
  hint,
  icon: Icon,
  tone = "brand",
  delay = 0,
  format = formatNumber,
}: Props) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out, delay }}
      className="card kpi"
    >
      <div className="kpi-head">
        <span className="kpi-label">{label}</span>
        {Icon ? (
          <span className={`kpi-icon ${tone}`}>
            <Icon size={16} />
          </span>
        ) : null}
      </div>
      <span className="kpi-value">
        {typeof value === "number" ? <AnimatedNumber value={value} format={format} /> : (value ?? "—")}
      </span>
      {hint ? <span className="kpi-hint">{hint}</span> : null}
    </motion.div>
  );
}