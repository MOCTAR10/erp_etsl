import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Clôture M3 (2026-10-18) : plan de charge avec capacité finie et alertes de surcharge.
test.describe("M3 Opérations : parcours de clôture", () => {
  test("le plan de charge s'affiche avec les ordres de fabrication", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/operations");
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Opérations/);
    await expect(page.getByText(/prévues/).first()).toBeVisible();
  });

  test("affectation des équipes et registre de présence sont saisissables", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/operations");
    await expect(page.getByRole("heading", { name: /Affectation des équipes/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Affecter une équipe" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Registre de présence chantier/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Relever une présence" })).toBeVisible();
  });
});
