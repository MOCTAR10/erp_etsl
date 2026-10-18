import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M11 : seuils de sous-activité et doctrine Mix A/B/C paramétrables par ETSL, valeurs provisoires signalées.
test.describe("M11 Contrôle de gestion : paramètres de pilotage", () => {
  test("un paramètre provisoire est signalé, modifié puis confirmé par la finance", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/controle-gestion");
    const section = page.getByTestId("pilotage-gestion");
    await expect(section.getByTestId("alerte-provisoire-gestion")).toContainText(/provisoire/);
    await expect(section.getByRole("cell", { name: "Mix A", exact: true })).toBeVisible();

    const ligne = section.getByRole("row", { name: /Sous-activité maximale du centre 90/ });
    // Valeur différente de l'actuelle : une valeur inchangée resterait « confirmée » d'une exécution à l'autre.
    const actuelle = /(?<![\d.])5(\.00)? %/.test(await ligne.innerText()) ? "6" : "5";
    await ligne.getByRole("button", { name: "Modifier" }).click();
    await ligne.getByRole("spinbutton").fill(actuelle);
    await ligne.getByRole("button", { name: "Valider" }).click();
    await expect(ligne).toContainText(new RegExp(`(?<![\\d.])${actuelle}(\\.00)? %`));

    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();
  });
});
