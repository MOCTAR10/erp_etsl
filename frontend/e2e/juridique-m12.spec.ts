import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M12 : recherche juridique liée aux objets métier M1-M11 ; types de documents officiels (signés et scellés)
// dont la liste est provisoire jusqu'à confirmation par ETSL.
test.describe("M12 Juridique : recherche liée et documents officiels", () => {
  test("un document est retrouvé avec l'affaire à laquelle il est lié", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/juridique");
    const section = page.getByTestId("recherche-juridique");
    await section.getByLabel("Terme recherché").fill("Oveng");
    await section.getByRole("button", { name: "Rechercher" }).click();
    const resultats = section.getByTestId("resultats-recherche");
    await expect(resultats).toContainText("Convention cadre de maintenance Oveng");
    await expect(resultats).toContainText("M1");
  });

  test("un type officiel est marqué (provisoire), confirmé puis retiré", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/juridique");
    const section = page.getByTestId("documents-officiels");
    const ligne = section.getByRole("row", { name: /Documents bancaires/ });
    await ligne.getByRole("button", { name: "Marquer officiel" }).click();
    await expect(ligne.getByText("Provisoire")).toBeVisible();
    await expect(section.getByTestId("alerte-provisoire-officiels")).toContainText(/provisoire/);

    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();

    await ligne.getByRole("button", { name: "Retirer" }).click();
    await expect(ligne.getByRole("button", { name: "Marquer officiel" })).toBeVisible();
  });
});
