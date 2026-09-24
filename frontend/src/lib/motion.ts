/**
 * Presets de mouvement centralisés (Motion v13) — dérivés de `theme/tokens.ts`.
 * Un seul endroit pour les transitions de page, staggers et entrées de cartes.
 */
import { motionTokens } from "../theme/tokens";
import type { Variants } from "motion/react";

/** Transition de page standard (withPilot, pages nichées). */
export const pageTransition = {
  duration: motionTokens.duration.base,
  ease: motionTokens.ease.out,
} as const;

/** Transition de module de carte de board (planche/grille). */
export const itemRefresh = {
  duration: motionTokens.duration.fast,
  ease: motionTokens.ease.out,
} as const;

/** Conteneur stagger — parent de `staggerItem`. */
export const staggerContainer = (stagger: number = motionTokens.stagger.quick): Variants => ({
  hidden: {},
  visible: { transition: { staggerChildren: stagger } },
});

/** Enfant stagger : fade + translation + legere echelle. */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: motionTokens.distance.xs, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: motionTokens.duration.base, ease: motionTokens.ease.out },
  },
};

/** Entrée générique fade+haut injectable en `initial`/`animate`/`transition`. */
export function fadeUp(delay = 0) {
  return {
    initial: { opacity: 0, y: motionTokens.distance.sm },
    animate: { opacity: 1, y: 0 },
    transition: { duration: motionTokens.duration.base, ease: motionTokens.ease.out, delay },
  };
}

/** Entrée de carte de board (kanban) — utilisable directement sur une motion.div. */
export const boardCardMotion = {
  initial: { opacity: 0, y: motionTokens.distance.xs, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, scale: 0.96 },
  transition: itemRefresh,
} as const;