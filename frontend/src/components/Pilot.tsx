import { motion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { motionTokens } from "../theme/tokens";
import { pageTransition, staggerContainer, staggerItem } from "../lib/motion";

/** Transition de page pilote — fade + légère translation (tokens partagés). */
export function withPilot(node: ReactNode): ReactNode {
  return (
    <motion.div
      initial={{ opacity: 0, y: motionTokens.distance.sm }}
      animate={{ opacity: 1, y: 0 }}
      transition={pageTransition}
    >
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
    <MotionConfig reducedMotion="user" transition={{ duration: motionTokens.duration.base }}>
      {children}
    </MotionConfig>
  );
}