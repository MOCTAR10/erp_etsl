/**
 * Tokens de mouvement partagés (Motion v13 / MIT) — BENCHMARK_ODOO_ETSL.md §6.
 * Une durée/mise en scène unique pour toute l'application, respecte reduced-motion.
 */
export const motionTokens = {
  duration: { fast: 0.16, base: 0.3, slow: 0.55 },
  ease: { out: [0.16, 1, 0.3, 1] as const, inOut: [0.65, 0, 0.35, 1] as const },
  stagger: { quick: 0.05, base: 0.1 },
  distance: { xs: 4, sm: 8, md: 16, lg: 28 },
} as const;

export type Duration = keyof typeof motionTokens.duration;
export type Distance = keyof typeof motionTokens.distance;