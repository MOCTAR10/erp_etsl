/**
 * Design system ETSL frontend — tokens uniques.
 * - motionTokens : mouvement (Motion v13) — BENCHMARK_ODOO_ETSL.md §6.
 * - designTokens : espacement, rayons, tailles, poids, ombres.
 * - palette     : couleurs charte (bleu/orange) exposées en JS (Recharts,
 *   inline styles) — les valeurs doivent rester SYNCHRONISÉES avec les CSS
 *   custom properties de `src/styles/global.css` (même hex). Source de vérité
 *   unique ici ; le CSS dérive.
 */

export const motionTokens = {
  duration: { fast: 0.16, base: 0.3, slow: 0.55 },
  ease: { out: [0.16, 1, 0.3, 1] as const, inOut: [0.65, 0, 0.35, 1] as const },
  stagger: { quick: 0.05, base: 0.1 },
  distance: { xs: 4, sm: 8, md: 16, lg: 28 },
} as const;

export const designTokens = {
  radius: { sm: 8, md: 10, lg: 12, xl: 16 },
  space: { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 },
  font: {
    xs: 12,
    sm: 13,
    md: 14,
    lg: 16,
    xl: 20,
    "2xl": 26,
  },
  weight: { regular: 400, medium: 500, semibold: 600, bold: 700 },
  shadow: {
    card: "0 1px 2px rgb(16 24 40 / 0.06), 0 4px 12px rgb(16 24 40 / 0.05)",
    pop: "0 4px 16px rgb(16 24 40 / 0.10), 0 12px 32px rgb(16 24 40 / 0.08)",
  },
  grid: { kpi: "repeat(auto-fit, minmax(190px, 1fr))", board: "repeat(auto-fit, minmax(230px, 1fr))" },
} as const;

export interface ThemeColors {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  text: string;
  textMuted: string;
  brand: string;
  brandSoft: string;
  accent: string;
  accentSoft: string;
  ok: string;
  okSoft: string;
  warn: string;
  warnSoft: string;
  err: string;
  errSoft: string;
}

export const palette = {
  light: {
    bg: "#f4f6fa",
    surface: "#ffffff",
    surface2: "#eef1f6",
    border: "#dde3ec",
    text: "#101828",
    textMuted: "#667085",
    brand: "#0b3a8c",
    brandSoft: "#e8eefb",
    accent: "#f59e0b",
    accentSoft: "#fdf1da",
    ok: "#16a34a",
    okSoft: "#e7f6ec",
    warn: "#d97706",
    warnSoft: "#fdeed7",
    err: "#dc2626",
    errSoft: "#fde8e8",
  },
  dark: {
    bg: "#0b1020",
    surface: "#131a2e",
    surface2: "#1b2440",
    border: "#26304e",
    text: "#e8edf7",
    textMuted: "#93a0be",
    brand: "#7aa2ff",
    brandSoft: "rgba(122, 162, 255, 0.14)",
    accent: "#fbbf24",
    accentSoft: "rgba(251, 191, 36, 0.14)",
    ok: "#34d399",
    okSoft: "rgba(52, 211, 153, 0.14)",
    warn: "#fbbf24",
    warnSoft: "rgba(251, 191, 36, 0.14)",
    err: "#f87171",
    errSoft: "rgba(248, 113, 113, 0.14)",
  },
} as const;

export type ThemeMode = "light" | "dark";

/** Palette du mode courant (lecture du `data-theme` courant ou du mode passé). */
export function paletteFor(mode: ThemeMode = readThemeMode()): ThemeColors {
  return palette[mode];
}

export function readThemeMode(): ThemeMode {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export type Duration = keyof typeof motionTokens.duration;
export type Distance = keyof typeof motionTokens.distance;
export type Space = keyof typeof designTokens.space;
export type FontSize = keyof typeof designTokens.font;
export type Radius = keyof typeof designTokens.radius;