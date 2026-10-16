import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

test.describe("Régression : espace libre-service salarié (CL-OM-01)", () => {
  test("un salarié lié voit son solde de congés et ses bulletins diffusés", async ({ page }) => {
    await loginAs(page, DEMO_USERS.salarie);
    await page.goto("/mon-espace");
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(/Mon espace salarié/);
    await expect(page.getByText("Solde de congé annuel")).toBeVisible();
    await expect(page.getByText("Mes bulletins de paie").first()).toBeVisible();
  });

  test("un compte sans fiche salarié est informé, sans erreur", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await page.goto("/mon-espace");
    await expect(page.getByText(/Aucune fiche salarié n'est liée/)).toBeVisible();
  });
});
