/**
 * Design system ETSL frontend — tokens uniques.
 * - motionTokens : mouvement (Motion v13) — BENCHMARK_ODOO_ETSL.md §6.
 * - designTokens : espacement, rayons, tailles, poids, ombres.
 * - palette     : couleurs charte (bleu/rouge du logo ETSL) exposées en JS (Recharts,
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
  /** Rayons (§3.3) : un ERP sérieux est peu arrondi. `xl` ne sert qu'aux surfaces flottantes. */
  radius: { xs: 6, sm: 8, md: 10, lg: 12, xl: 16, full: 999 },
  /** Espacements base 4, rythme 8 (§3.2) — même échelle que `--space-*`. */
  space: { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40 },
  /** Échelle typographique (§3.1) : taille / interligne en px — même échelle que `--fs-*` / `--lh-*`. */
  font: {
    display: { size: 40, line: 44 },
    h1: { size: 24, line: 32 },
    h2: { size: 18, line: 26 },
    h3: { size: 15, line: 22 },
    kpi: { size: 28, line: 32 },
    body: { size: 14, line: 20 },
    sm: { size: 13, line: 18 },
    xs: { size: 12, line: 16 },
  },
  weight: { regular: 400, medium: 500, semibold: 600, strong: 650, bold: 700 },
  /** Hauteurs de contrôles : petit (tableaux, cartes), défaut, terrain / mobile. */
  control: { sm: 32, md: 36, lg: 44 },
  /** 3 niveaux d'ombre seulement (§3.4) ; plus de halo coloré. */
  shadow: {
    xs: "0 1px 2px rgb(16 24 40 / 0.04)",
    md: "0 4px 12px rgb(16 24 40 / 0.08), 0 1px 3px rgb(16 24 40 / 0.06)",
    pop: "0 12px 32px rgb(16 24 40 / 0.14), 0 2px 6px rgb(16 24 40 / 0.08)",
  },
} as const;

export interface ThemeColors {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  borderStrong: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  brand: string;
  brandDeep: string;
  brandHover: string;
  brandSoft: string;
  brandTint: string;
  onBrand: string;
  ring: string;
  accent: string;
  accentSoft: string;
  steel: string;
  steelSoft: string;
  ok: string;
  okSoft: string;
  okText: string;
  warn: string;
  warnSoft: string;
  warnText: string;
  err: string;
  errSoft: string;
  errText: string;
  info: string;
  infoSoft: string;
  infoText: string;
}

export const palette = {
  light: {
    bg: "#f6f7fb",
    surface: "#ffffff",
    surface2: "#f1f3f8",
    border: "#e3e7ef",
    borderStrong: "#cfd6e3",
    text: "#0f172a",
    textMuted: "#5b6578",
    textSubtle: "#8a93a6",
    brand: "#12308f",
    brandDeep: "#0a1f66",
    brandHover: "#0a1f66",
    brandSoft: "#e9edfa",
    brandTint: "#d8e0f7",
    onBrand: "#ffffff",
    ring: "rgba(18, 48, 143, 0.40)",
    accent: "#d4142a",
    accentSoft: "#fde9ec",
    steel: "#4f5f86",
    steelSoft: "#eaedf4",
    ok: "#16a34a",
    okSoft: "#e7f6ec",
    okText: "#14743a",
    warn: "#d97706",
    warnSoft: "#fdeed7",
    warnText: "#9a4a07",
    err: "#dc2626",
    errSoft: "#fde8e8",
    errText: "#b91c1c",
    info: "#2563eb",
    infoSoft: "#e8effd",
    infoText: "#1d4ed8",
  },
  dark: {
    bg: "#0b1020",
    surface: "#151c33",
    surface2: "#1c2541",
    border: "#2a3557",
    borderStrong: "#3a4770",
    text: "#e8edf7",
    textMuted: "#9aa7c6",
    textSubtle: "#7684a8",
    brand: "#7f9cf5",
    brandDeep: "#16255c",
    brandHover: "#9bb2f8",
    brandSoft: "rgba(127, 156, 245, 0.14)",
    brandTint: "rgba(127, 156, 245, 0.24)",
    onBrand: "#0b1020",
    ring: "rgba(127, 156, 245, 0.60)",
    accent: "#f0475a",
    accentSoft: "rgba(240, 71, 90, 0.14)",
    steel: "#a3b2d6",
    steelSoft: "rgba(163, 178, 214, 0.14)",
    ok: "#34d399",
    okSoft: "rgba(52, 211, 153, 0.14)",
    okText: "#34d399",
    warn: "#fbbf24",
    warnSoft: "rgba(251, 191, 36, 0.14)",
    warnText: "#fbbf24",
    err: "#f87171",
    errSoft: "rgba(248, 113, 113, 0.14)",
    errText: "#f87171",
    info: "#60a5fa",
    infoSoft: "rgba(96, 165, 250, 0.14)",
    infoText: "#93c5fd",
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
export type Shadow = keyof typeof designTokens.shadow;