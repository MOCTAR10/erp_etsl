import { motion } from "motion/react";
import type { CSSProperties, ReactNode } from "react";

import { motionTokens } from "../../theme/tokens";
import { Badge } from "../ui";

export type HeroTone = "ok" | "warn" | "err" | "neutral";

/** Tonalité d'un taux (en %) selon ses seuils : vert à partir de `ok`, orange à partir de `warn`, rouge en dessous. */
export function toneFor(value: number, ok: number, warn: number): HeroTone {
  if (value >= ok) return "ok";
  if (value >= warn) return "warn";
  return "err";
}

/**
 * Chiffre héros de la page Direction : libellé en clair, valeur (40 px), état par rapport à l'objectif,
 * jauge à seuils (zones rouge / orange / verte + repère d'objectif) et indication de contexte.
 */
export function HeroStat({
  label,
  value,
  unit,
  tone = "neutral",
  status,
  gauge,
  foot,
  hint,
  compact = false,
  delay = 0,
}: {
  label: string;
  value: ReactNode;
  /** Unité affichée plus petite à droite de la valeur (« FCFA », « jours »…). */
  unit?: ReactNode;
  tone?: HeroTone;
  /** Pastille d'état (« Sous l'objectif »…) en haut à droite. */
  status?: string;
  /** Jauge à seuils : valeur et objectif en %, seuils orange et vert. */
  gauge?: { value: number; target: number; warn: number; ok: number; label: string };
  /** Ligne d'objectif / d'écart sous la jauge. */
  foot?: ReactNode;
  hint?: ReactNode;
  /** Valeur longue (montant exact) : police réduite plutôt qu'abréviation. */
  compact?: boolean;
  delay?: number;
}) {
  const pct = gauge ? Math.min(100, Math.max(0, gauge.value)) : 0;
  return (
    <motion.article
      className={`card dir-hero tone-${tone}`}
      initial={{ opacity: 0, y: motionTokens.distance.xs }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out, delay }}
    >
      <header className="dir-hero-head">
        <h3 className="dir-hero-label">{label}</h3>
        {status ? <Badge tone={tone === "neutral" ? "neutral" : tone}>{status}</Badge> : null}
      </header>
      <p className={`dir-hero-value${compact ? " is-compact" : ""}`}>
        <span className="dir-hero-number">{value}</span>
        {unit ? <span className="dir-hero-unit">{unit}</span> : null}
      </p>
      {gauge ? (
        <div
          className="dir-gauge"
          role="progressbar"
          aria-label={gauge.label}
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
          style={{ "--warn-at": `${gauge.warn}%`, "--ok-at": `${gauge.ok}%` } as CSSProperties}
        >
          <span className="dir-gauge-fill" style={{ width: `${pct}%` }} />
          <span className="dir-gauge-target" style={{ left: `${gauge.target}%` }} aria-hidden />
        </div>
      ) : null}
      {foot ? <div className="dir-hero-foot">{foot}</div> : null}
      {hint ? <p className="dir-hero-hint">{hint}</p> : null}
    </motion.article>
  );
}
