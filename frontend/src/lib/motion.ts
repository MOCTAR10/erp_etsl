/**
 * Presets de mouvement centralisés (Motion v13) — dérivés de `theme/tokens.ts`.
 * Un seul endroit pour les transitions de page, staggers et entrées de cartes.
 * Règle premium : 120–200 ms, fondu + translation de 4 px, jamais d'échelle à l'entrée ;
 * `layout` réservé aux cartes qui changent réellement de colonne. `MotionProvider`
 * (`reducedMotion="user"`) neutralise les translations quand l'OS demande moins de mouvement.
 */
import { motionTokens } from "../theme/tokens";
import type { Transition, Variants } from "motion/react";

/** Transition de page standard (withPilot, pages nichées) : 160 ms. */
export const pageTransition = {
  duration: motionTokens.duration.fast,
  ease: motionTokens.ease.out,
} as const;

/** Entrée de page : fondu + 4 px, sans échelle (à étaler sur une motion.div). */
export const pageEnter = {
  initial: { opacity: 0, y: motionTokens.distance.xs },
  animate: { opacity: 1, y: 0 },
  transition: pageTransition,
} as const;

/** Transition de module de carte de board (planche/grille) : 120 ms. */
export const itemRefresh = {
  duration: motionTokens.duration.instant,
  ease: motionTokens.ease.out,
} as const;

/** Déplacement d'une carte d'une colonne à l'autre (prop `layout="position"`) : 200 ms, sans rebond. */
export const layoutMove: Transition = {
  layout: { duration: motionTokens.duration.base, ease: motionTokens.ease.inOut },
};

/** Conteneur stagger — parent de `staggerItem`. */
export const staggerContainer = (stagger: number = motionTokens.stagger.quick): Variants => ({
  hidden: {},
  visible: { transition: { staggerChildren: stagger } },
});

/** Enfant stagger : fondu + translation de 4 px (pas d'échelle : pas de « flottement » au chargement). */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: motionTokens.distance.xs },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: motionTokens.duration.fast, ease: motionTokens.ease.out },
  },
};

/** Entrée générique fade+haut injectable en `initial`/`animate`/`transition`. */
export function fadeUp(delay = 0) {
  return {
    initial: { opacity: 0, y: motionTokens.distance.xs },
    animate: { opacity: 1, y: 0 },
    transition: { duration: motionTokens.duration.fast, ease: motionTokens.ease.out, delay },
  };
}

/**
 * Carte de board (kanban) — à étaler sur une motion.div avec `layout="position"` sous un
 * `AnimatePresence` : entrée 120 ms, sortie en fondu, glissement de 200 ms vers la nouvelle colonne.
 */
export const boardCardMotion = {
  initial: { opacity: 0, y: motionTokens.distance.xs },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0 },
  transition: { ...itemRefresh, ...layoutMove },
} as const;
