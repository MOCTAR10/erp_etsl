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
  radius: { sm: 8, md: 10, lg: 14, xl: 18, "2xl": 24 },
  space: { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 },
  font: {
    xs: 12,
    sm: 13,
    md: 14,
    lg: 16,
    xl: 20,
    "2xl": 24,
    "3xl": 32,
  },
  weight: { regular: 400, medium: 500, semibold: 600, bold: 700, extrabold: 800 },
  shadow: {
    card: "0 1px 2px rgb(16 24 40 / 0.05), 0 6px 18px rgb(16 24 40 / 0.05)",
    pop: "0 10px 28px rgb(16 24 40 / 0.12), 0 22px 60px rgb(16 24 40 / 0.10)",
    brand: "0 6px 18px rgb(11 58 140 / 0.30)",
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
  brandDeep: string;
  brandSoft: string;
  brandTint: string;
  ring: string;
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
    textMuted: "#637083",
    brand: "#0b3a8c",
    brandDeep: "#082a62",
    brandSoft: "#e8eefb",
    brandTint: "#d9e5fb",
    ring: "rgba(11, 58, 140, 0.40)",
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
    surface: "#141b30",
    surface2: "#1b2440",
    border: "#26304e",
    text: "#e8edf7",
    textMuted: "#95a2c2",
    brand: "#7aa2ff",
    brandDeep: "#152a52",
    brandSoft: "rgba(122, 162, 255, 0.14)",
    brandTint: "rgba(122, 162, 255, 0.22)",
    ring: "rgba(122, 162, 255, 0.60)",
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