import { motion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { motionTokens } from "../theme/tokens";
import { pageEnter, staggerContainer, staggerItem } from "../lib/motion";

/** Transition de page pilote — fondu 160 ms + translation de 4 px (preset partagé `pageEnter`). */
export function withPilot(node: ReactNode): ReactNode {
  return (
    <motion.div {...pageEnter}>
      {node}
    </motion.div>
  );
}

/** Conteneur animé (stagger) pour grilles de cartes KPIs. */
export function MotionGrid({ children }: { children: ReactNode }) {
  return (
    <motion.div
      className="kpi-grid"
      initial="hidden"
      animate="visible"
      variants={staggerContainer()}
    >
      {children}
    </motion.div>
  );
}

export function MotionItem({ children }: { children: ReactNode }) {
  return (
    <motion.div
      className="motion-item"
      variants={staggerItem}
    >
      {children}
    </motion.div>
  );
}

/** Force libère le contrôle au moteur : respecte prefers-reduced-motion de l'OS. */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: motionTokens.duration.fast, ease: motionTokens.ease.out }}>
      {children}
    </MotionConfig>
  );
}