import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M10 : paramètres de clôture/lettrage modifiables par ETSL, valeurs provisoires signalées.
test.describe("M10 Comptabilité : paramètres de lettrage", () => {
  test("un paramètre provisoire est signalé, modifié puis confirmé par la finance", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/comptabilite");
    await expect(page.getByTestId("alerte-provisoire-compta")).toContainText(/provisoire/);

    const ligne = page.getByRole("row", { name: /Tolérance d'écart de lettrage/ });
    await ligne.getByRole("button", { name: "Modifier" }).click();
    await ligne.getByRole("spinbutton").fill("5");
    await ligne.getByRole("button", { name: "Valider" }).click();
    await expect(ligne).toContainText("5");

    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();
  });
});
