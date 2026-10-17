import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Clôture M1 (2026-10-17) : parcours commercial — offres versionnées, affaires, contrats signés, marges par axe.
test.describe("M1 Commercial : parcours de clôture", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/pipeline");
  });

  test("offres, affaires, contrats et marges sont pilotables depuis le pipeline", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Pipeline commercial/);
    for (const titre of [/Offres \(versions\)/, /Affaires/, /Contrats \(CLM\)/, /Marges par axe/]) {
      await expect(page.getByText(titre).first()).toBeVisible();
    }
    await expect(page.getByText("Pipe pondéré")).toBeVisible();
    const axe = page.getByRole("combobox", { name: /Marges par axe/ });
    await axe.selectOption("responsable");
    await expect(page.getByRole("columnheader", { name: "Responsable d'affaire" })).toBeVisible();
  });
});
