import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: path.join(__dirname, "e2e"),
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  // Le frontend est servi par le dev server Vite (proxy /api → 127.0.0.1:8000).
  // Le backend Django doit tourner sur la base seedée `etls_e2e` (voir
  // archi/AGENTS.md "Régression"). webServer = le lanceur Vite Playwright.
  webServer: {
    command: "npx vite --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  // La régression E2E tourne contre la base de démo dédiée `etls_e2e` seedée.
  // Le backend (Django) doit être lancé via scripts/regression/start_dev.ps1 ;
  // le runserver attendu sur 127.0.0.1:8000, Vite proxyé sur 5173.
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
  ],
});