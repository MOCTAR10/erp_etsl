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

test.describe("Régression : modules du menu (RF-59)", () => {
  test("admin (12 modules) voit tous les liens métier", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    const sidebar = page.locator(".sidebar");
    for (const label of [/Pipeline/, /Commandes/, /Opérations/, /Comptabilité/, /Juridique/]) {
      await expect(sidebar.getByRole("link", { name: label })).toBeVisible();
    }
  });

  test("rh ne voit que ses 2 modules dans le menu", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh, DEMO_PASSWORD);
    const sidebar = page.locator(".sidebar");
    await expect(sidebar.getByRole("link", { name: /RH & Paie/ })).toBeVisible();
    await expect(sidebar.getByRole("link", { name: /HSE/ })).toBeVisible();
    // Modules hors `ROLE_MODULES[rh]` : liens absents, donc pas de 403 au clic.
    for (const label of [/Comptabilité/, /Juridique/, /Stocks/, /Commandes/]) {
      await expect(sidebar.getByRole("link", { name: label })).toHaveCount(0);
    }
  });

  test("rh atterrit sur un module qu'il peut lire", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh, DEMO_PASSWORD);
    await expect(page).toHaveURL(/\/rh-paie/);
    await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
  });
});