import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

test.describe("Régression : sécurité des montants (RF-59)", () => {
  test("admin (cercle montants) voit les montants des commandes", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/purchases");
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(/Achats/);
    // Au moins une commande seedée (seed_achats_demo) — aucun montant masqué pour admin.
    await expect(page.locator(".task-card").first()).toBeVisible();
    await expect(page.locator("text=Montant restreint")).toHaveCount(0);
  });

  test("atelier (hors cercle montants achats) voit « Montant restreint »", async ({ page }) => {
    await loginAs(page, DEMO_USERS.atelier, DEMO_PASSWORD);
    await page.goto("/purchases");
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(/Achats/);
    await expect(page.locator(".task-card").first()).toBeVisible();
    await expect(page.locator("text=Montant restreint").first()).toBeVisible();
  });
});