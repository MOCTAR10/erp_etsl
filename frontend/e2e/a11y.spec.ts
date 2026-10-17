import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Audit d'accessibilité automatisé (axe-core, WCAG 2.1 A/AA) : toute violation « serious » ou « critical »
// fait échouer la régression. Animations coupées (reduced-motion) pour ne pas mesurer des opacités transitoires.
const ROUTES = [
  "/", "/kanban", "/circuits", "/notifications", "/pipeline", "/purchases", "/operations", "/logistique",
  "/stocks", "/qualite", "/hse", "/maintenance", "/rh-paie", "/comptabilite", "/controle-gestion",
  "/juridique", "/direction", "/signatures", "/terrain", "/mon-espace",
];

async function audit(page: Page) {
  // Motion garde les fondus d'opacité même en reduced-motion : on attend la fin des animations,
  // sinon axe mesure un contraste sur un élément à demi transparent (faux positif).
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"));
  await page.waitForTimeout(700);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const blocking = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}) : ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(blocking, blocking.join("\n")).toEqual([]);
}

test.use({ reducedMotion: "reduce" });

test("a11y : page de connexion", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /Se connecter/ })).toBeVisible();
  await audit(page);
});

test.describe("a11y : pages de l'application", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
  });

  for (const path of ROUTES) {
    for (const theme of ["light", "dark"] as const) {
      test(`${path} (${theme})`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
        await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
        await page.waitForLoadState("networkidle");
        await audit(page);
      });
    }
  }
});
