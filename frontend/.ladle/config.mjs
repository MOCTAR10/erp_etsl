// Catalogue Ladle du kit UI (`npm run ladle`, `npm run ladle:build`) — outil de revue, hors build applicatif et hors CI.
/** @type {import('@ladle/react').UserConfig} */
export default {
  stories: "src/**/*.stories.tsx",
  // Ladle embarque son propre Vite : configuration dédiée (sans le proxy /api ni le plugin React du projet).
  viteConfig: ".ladle/vite.config.ts",
  outDir: "build-ladle",
  addons: {
    theme: { enabled: true, defaultState: "light" },
    width: {
      enabled: true,
      options: { mobile: 390, tablette: 768, bureau: 1440 },
      defaultState: 0,
    },
    rtl: { enabled: false },
    a11y: { enabled: true },
    source: { enabled: true },
    ladle: { enabled: false },
  },
};
