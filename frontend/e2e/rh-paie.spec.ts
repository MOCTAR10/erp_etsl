import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M9 : barèmes de paie paramétrables, valeurs provisoires signalées jusque sur les bulletins.
test.describe("M9 RH & Paie : paramétrage des barèmes", () => {
  test("un barème provisoire est signalé, puis confirmé par le cercle paie", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await page.goto("/rh-paie");
    await expect(page.getByTestId("alerte-provisoire")).toContainText(/provisoire/);

    const code = `E2E-${Date.now() % 100000}`;
    await page.getByPlaceholder("Code").fill(code);
    await page.getByPlaceholder("Libellé").fill("Barème m9 e2e");
    await page.getByPlaceholder("Taux (%)").fill("1.5");
    await page.getByLabel("Date d'effet").fill("2026-01-01");
    await page.getByRole("button", { name: "Enregistrer" }).click();

    const ligne = page.getByRole("row", { name: new RegExp(code) });
    await expect(ligne.getByText("Provisoire")).toBeVisible();
    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();

    await ligne.getByRole("button", { name: "Historique" }).click();
    await expect(page.getByText(/confirmation/)).toBeVisible();
  });

  test("les paramètres de paie (SMIG, durée légale) sont visibles", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await page.goto("/rh-paie");
    await expect(page.getByText("DUREE_LEGALE_HEBDO")).toBeVisible();
    await expect(page.getByText("SMIG", { exact: true })).toBeVisible();
  });
});
