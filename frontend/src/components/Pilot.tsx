import { motion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { motionTokens } from "../theme/tokens";

/** Transition de page pilote — fade + légère translation (tokens partagés). */
export function withPilot(node: ReactNode): ReactNode {
  return (
    <motion.div
      initial={{ opacity: 0, y: motionTokens.distance.sm }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: motionTokens.duration.base,
        ease: motionTokens.ease.out,
      }}
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
      variants={{
        hidden: {},
        visible: {
          transition: { staggerChildren: motionTokens.stagger.quick },
        },
      }}
    >
      {children}
    </motion.div>
  );
}

export function MotionItem({ children }: { children: ReactNode }) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: motionTokens.distance.xs },
        visible: {
          opacity: 1,
          y: 0,
          transition: {
            duration: motionTokens.duration.base,
            ease: motionTokens.ease.out,
          },
        },
      }}
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