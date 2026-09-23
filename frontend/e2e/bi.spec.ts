import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

test.describe("Régression : Direction / BI (couche D)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
  });

  test("dashboard direction : sections C1/C2/C3 présentes", async ({ page }) => {
    await page.goto("/direction");
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(/Direction \/ BI/);

    // C1 — KPIs Direction.
    await expect(page.getByText("Tableau de bord Direction (C1)").first()).toBeVisible();

    // C2 — Reporting pétrolier (ASMR / HSE / Qualité).
    await expect(page.getByText("Reporting client pétrolier (C2)").first()).toBeVisible();
    await expect(page.getByText("NC ouvertes", { exact: true })).toBeVisible();

    // C3 — Alertes d'échéance.
    const alertes = page.getByText(/Alertes d'échéance \(C3\)/).first();
    await expect(alertes).toBeVisible();
  });

  test("KPIs C1 chargent des valeurs numériques (rétention GED, effectif RH)", async ({ page }) => {
    await page.goto("/direction");
    const docsKpi = page.locator(".kpi", { hasText: "Rétention GED" }).first();
    await expect(docsKpi.locator(".kpi-value")).not.toBeEmpty();
    const rhKpi = page.locator(".kpi", { hasText: "RH & Paie" }).first();
    await expect(rhKpi.locator(".kpi-value")).not.toBeEmpty();
  });

  test("l'utilisateur logistique voit ses montants masqués sur le dashboard direction", async ({ page: page }) => {
    await loginAs(page, DEMO_USERS.logistique, DEMO_PASSWORD);
    await page.goto("/direction");
    // Le CA gagné (commercial) est masqué en « •••••• ».
    await expect(page.locator("text=••••••").first()).toBeVisible();
  });
});