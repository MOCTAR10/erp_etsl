import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Tests visuels (`npm run test:visual`) : 10 écrans × clair / sombre / mobile comparés à des captures de référence.
 * Projet SÉPARÉ de la régression E2E (`playwright.config.ts`) et absent de la CI : le rendu des polices dépend
 * du système, les références se génèrent et se rejouent dans le conteneur `mcr.microsoft.com/playwright:v1.63.0-noble`
 * (mode d'emploi : `frontend/DESIGN_SYSTEM.md` § Tests visuels).
 * Frontend = build de production servi par `vite preview` (port 4173), backend = base de démo seedée
 * (`VITE_API_TARGET`, défaut http://127.0.0.1:8000 ; serveur de dev : http://127.0.0.1:8100).
 */
const PORT = Number(process.env.VISUEL_PORT || 4173);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const SESSION = path.join(__dirname, "e2e/visuel/.auth/admin.json");

export default defineConfig({
  testDir: path.join(__dirname, "e2e/visuel"),
  // Suffixe propre (`*.visuel.ts`) : jamais ramassé par `npm run test:e2e` (motif par défaut *.spec.ts / *.test.ts).
  testMatch: /.*\.visuel\.ts$/,
  // Références locales, non versionnées (générées dans le conteneur, voir DESIGN_SYSTEM.md).
  snapshotPathTemplate: "{testDir}/references/{projectName}/{arg}{ext}",
  outputDir: path.join(__dirname, "test-results/visuel"),
  timeout: 90_000,
  expect: {
    timeout: 20_000,
    toHaveScreenshot: {
      // Tolérance faible : absorbe l'anticrénelage, pas un changement de mise en page.
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
      animations: "disabled",
      caret: "hide",
      scale: "css",
    },
  },
  fullyParallel: true,
  workers: Number(process.env.PW_WORKERS || 1),
  retries: 0,
  reporter: [["html", { open: "never", outputFolder: "playwright-report/visuel" }], ["list"]],
  use: {
    baseURL: BASE_URL,
    locale: "fr-FR",
    timezoneId: "Africa/Libreville",
    trace: "retain-on-failure",
  },
  webServer: {
    command: process.env.PW_WEB_CMD || `npx vite build --logLevel warn && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `${BASE_URL}/login`,
    reuseExistingServer: true,
    timeout: 240_000,
  },
  projects: [
    { name: "connexion", testMatch: /connexion\.visuel\.ts$/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "clair",
      testIgnore: /connexion\.visuel\.ts$/,
      dependencies: ["connexion"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, storageState: SESSION },
    },
    {
      name: "sombre",
      testIgnore: /connexion\.visuel\.ts$/,
      dependencies: ["connexion"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, colorScheme: "dark", storageState: SESSION },
    },
    {
      name: "mobile",
      testIgnore: /connexion\.visuel\.ts$/,
      dependencies: ["connexion"],
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 2,
        isMobile: true,
        hasTouch: true,
        storageState: SESSION,
      },
    },
  ],
});
