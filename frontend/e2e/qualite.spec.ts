import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Clôture M6 (2026-10-18) : métrologie, registre des joints, épreuves P/T et approbation de l'ITP.
test.describe("M6 Qualité : parcours de clôture", () => {
  test("l'écran Qualité expose métrologie, joints, épreuves et l'approbation de l'ITP", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/qualite");
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Qualité/);
    await expect(page.getByText(/Métrologie \(étalonnage\)/).first()).toBeVisible();
    await expect(page.getByText(/Registre des joints soudés/).first()).toBeVisible();
    await expect(page.getByText(/Épreuves hydrauliques/).first()).toBeVisible();
  });
});
