import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Clôture M5 (2026-10-17) : valorisation mensuelle publiée à M11 et inventaires tournants planifiés.
test.describe("M5 Stocks : parcours de clôture", () => {
  test("la valorisation mensuelle se fige depuis l'écran Stocks", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/stocks");
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Stocks/);
    await expect(page.getByText(/Valorisation mensuelle/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Figer le mois" })).toBeVisible();
  });
});
