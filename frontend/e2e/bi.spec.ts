import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

test.describe("Régression : Direction / BI (couche D)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
  });

  test("dashboard direction : indicateurs par module, reporting pétrolier et échéances présents", async ({ page }) => {
    await page.goto("/direction");
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(/Direction \/ BI/);

    // Indicateurs Direction par module (aucun code d'exigence à l'écran).
    await expect(page.getByRole("heading", { name: "Indicateurs par module" })).toBeVisible();

    // Reporting pétrolier (ASMR / HSE / Qualité).
    await expect(page.getByRole("heading", { name: "Reporting client pétrolier" })).toBeVisible();
    await expect(page.getByText("NC ouvertes", { exact: true })).toBeVisible();

    // Alertes d'échéance.
    await expect(page.getByRole("heading", { name: /^Alertes d'échéance/ })).toBeVisible();
  });

  test("cockpit : « À traiter maintenant », tendances et accès direct aux modules", async ({ page }) => {
    await page.goto("/direction");
    await expect(page.getByRole("heading", { name: "À traiter maintenant" })).toBeVisible();
    await expect(page.getByText("Tendances sur 6 mois")).toBeVisible();
    await expect(page.getByText("Disponibilité du matériel").first()).toBeVisible();
    // une tuile KPI est un lien vers son module
    await page.locator("a.kpi-link", { hasText: "Incidents HSE ouverts" }).first().click();
    await expect(page).toHaveURL(/\/hse$/);
  });

  test("les indicateurs par module chargent des valeurs (opportunités, effectif)", async ({ page }) => {
    await page.goto("/direction");
    const opportunites = page.locator(".kpi", { hasText: "Opportunités ouvertes" }).first();
    await expect(opportunites.locator(".kpi-value")).not.toBeEmpty();
    const effectif = page.locator(".kpi", { hasText: "Effectif salarié" }).first();
    await expect(effectif.locator(".kpi-value")).not.toBeEmpty();
  });

  test("l'utilisateur logistique voit ses montants masqués sur le dashboard direction", async ({ page: page }) => {
    await loginAs(page, DEMO_USERS.logistique, DEMO_PASSWORD);
    await page.goto("/direction");
    // Le CA signé (commercial) est masqué en « •••••• ».
    await expect(page.locator("text=••••••").first()).toBeVisible();
  });
});
