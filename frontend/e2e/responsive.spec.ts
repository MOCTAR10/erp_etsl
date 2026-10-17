import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

test.describe("Régression : mobile (tiroir de navigation)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("le menu s'ouvre via le hamburger, navigue puis se referme", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/");

    const sidebar = page.locator("#app-sidebar");
    await expect(sidebar).not.toHaveClass(/open/);

    await page.getByRole("button", { name: "Menu" }).click();
    await expect(sidebar).toHaveClass(/open/);

    await sidebar.getByRole("link", { name: /Direction \/ BI/ }).click();
    await expect(page).toHaveURL(/\/direction$/);
    await expect(sidebar).not.toHaveClass(/open/);
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(/Direction \/ BI/);
  });

  test("pas de défilement horizontal de la page", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/direction");
    await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  const ROUTES = [
    "/", "/direction", "/kanban", "/circuits", "/notifications", "/pipeline", "/purchases",
    "/operations", "/logistique", "/stocks", "/qualite", "/hse", "/maintenance", "/rh-paie",
    "/comptabilite", "/controle-gestion", "/juridique", "/terrain", "/mon-espace", "/signatures",
  ];
  for (const route of ROUTES) {
    test(`${route} : aucun débordement horizontal du contenu`, async ({ page }) => {
      await loginAs(page, DEMO_USERS.admin);
      await page.goto(route);
      await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
      const overflow = await page.evaluate(() => {
        const main = document.querySelector(".main");
        return main ? main.scrollWidth - main.clientWidth : 0;
      });
      expect(overflow).toBeLessThanOrEqual(1);
    });
  }

  test("la déconnexion reste accessible dans le tiroir", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.getByRole("button", { name: "Menu" }).click();
    await page.locator("#app-sidebar").getByRole("button", { name: "Déconnexion" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
