import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M4 : paramètres de la formule glissante et de la valorisation GR paramétrables par ETSL, valeurs provisoires
// signalées ; coût GR du mois ventilé par affaire (flux compteurs -> M11, compte 618 isolé).
test.describe("M4 Logistique : paramètres GR et coût par affaire", () => {
  test("un paramètre provisoire est signalé, modifié puis confirmé", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/logistique");
    const section = page.getByTestId("parametres-logistique");
    await expect(section.getByTestId("alerte-provisoire-logistique")).toContainText(/provisoire/);

    const ligne = section.getByRole("row", { name: /jours par mois facturable/ });
    // Valeur différente de l'actuelle : une valeur inchangée resterait « confirmée » d'une exécution à l'autre.
    const actuelle = /(?<![\d.])30(\.00)? jours/.test(await ligne.innerText()) ? "31" : "30";
    await ligne.getByRole("button", { name: "Modifier" }).click();
    await ligne.getByRole("spinbutton").fill(actuelle);
    await ligne.getByRole("button", { name: "Valider" }).click();
    await expect(ligne).toContainText(new RegExp(`(?<![\\d.])${actuelle}(\\.00)? jours`));

    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();
  });

  test("le coût GR du mois est ventilé par affaire avec le compte 618", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/logistique");
    const section = page.getByTestId("gr-affaires");
    await expect(section).toContainText("Coût GLOBAL RENTAL par affaire");
    await expect(section).toContainText("(618)");
    await expect(section.getByLabel("Mois")).toBeVisible();
  });
});
