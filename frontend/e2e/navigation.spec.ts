import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

const ROUTES: { path: string; heading: RegExp }[] = [
  { path: "/", heading: /Tableau de bord/ },
  { path: "/pipeline", heading: /Pipeline commercial/ },
  { path: "/purchases", heading: /Achats/ },
  { path: "/operations", heading: /Opérations/ },
  { path: "/logistique", heading: /Logistique/ },
  { path: "/stocks", heading: /Stocks/ },
  { path: "/qualite", heading: /Qualité/ },
  { path: "/hse", heading: /HSE/ },
  { path: "/maintenance", heading: /Maintenance/ },
  { path: "/rh-paie", heading: /RH & Paie/ },
  { path: "/comptabilite", heading: /Comptabilité/ },
  { path: "/controle-gestion", heading: /Contrôle de gestion/ },
  { path: "/juridique", heading: /Juridique/ },
  { path: "/direction", heading: /Direction \/ BI/ },
];

test.describe("Régression : navigation (smoke)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
  });

  for (const { path, heading } of ROUTES) {
    test(`${path} charge`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator(".sidebar")).toBeVisible();
      await expect(page.locator(".main")).toBeVisible();
      await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(heading);
    });
  }
});