import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// Couche D : cubes OLAP à 6 axes alimentés depuis le grand livre, archive scellée et immuable conservée 10 ans
// (durée provisoire, modifiable et confirmable sans développeur).
test.describe("Couche D : cubes à 6 axes et archive 10 ans", () => {
  test("lecture par axe, alimentation, archive scellée et durée de conservation paramétrable", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/direction");
    // Les cubes sont rangés dans l'onglet « Cubes 6 axes » du pilotage financier.
    await page.getByRole("tab", { name: "Cubes 6 axes" }).click();
    const section = page.getByTestId("cube-olap");
    await expect(section).toContainText("grand livre");

    // Les six axes sont proposés ; la lecture suit les axes cochés.
    for (const axe of ["Affaire", "Chantier", "Site", "Activité", "Centre", "Période"]) {
      await expect(section.getByLabel(axe, { exact: true })).toBeVisible();
    }
    await section.getByLabel("Affaire", { exact: true }).check();
    await expect(section.getByTestId("cube-table").getByRole("columnheader", { name: "Affaire" })).toBeVisible();

    // Durée de conservation : valeur différente de l'actuelle, donc provisoire, puis confirmée.
    const params = section.getByTestId("parametres-cube");
    const ligne = params.getByRole("row", { name: /Conservation de l'archive/ });
    const actuelle = /(?<![\d.])10(\.00)? ans/.test(await ligne.innerText()) ? "12" : "10";
    await ligne.getByRole("button", { name: "Modifier" }).click();
    await ligne.getByRole("spinbutton").fill(actuelle);
    await ligne.getByRole("button", { name: "Valider" }).click();
    await expect(params.getByTestId("alerte-provisoire-cube")).toContainText(/provisoire/);
    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();

    // Alimentation idempotente du mois précédent (rejouable).
    await section.getByRole("button", { name: "Alimenter le cube" }).click();
    await expect(section.getByTestId("cube-info")).toContainText(/alimenté/);
    await section.getByRole("button", { name: "Alimenter le cube" }).click();
    await expect(section.getByTestId("cube-info")).toContainText(/alimenté/);

    // Archive d'une période ancienne (unique par exécution) : scellée, intègre, conservée jusqu'à +N ans.
    const n = Date.now() % 240;
    const periode = `${1990 + Math.floor(n / 12)}-${String((n % 12) + 1).padStart(2, "0")}`;
    await section.getByLabel("Mois", { exact: true }).fill(periode);
    page.once("dialog", (d) => void d.accept());
    await section.getByRole("button", { name: "Archiver la période" }).click();
    await expect(section.getByTestId("cube-info")).toContainText(`Cube ${periode} archivé`);
    const archive = section.getByTestId("cube-archives").getByRole("row", { name: new RegExp(periode) });
    await expect(archive).toContainText("Intégrité vérifiée");
    await expect(archive).toContainText("Conservé jusqu'au");

    // Une période archivée ne se recalcule plus.
    await section.getByRole("button", { name: "Alimenter le cube" }).click();
    await expect(section.getByRole("alert")).toContainText(/archiv/);
  });

  test("un rôle hors du cercle des montants ne voit pas les cubes", async ({ page }) => {
    await loginAs(page, DEMO_USERS.logistique);
    await page.goto("/direction");
    await expect(page.getByRole("heading", { name: "Indicateurs par module" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Cubes 6 axes" })).toHaveCount(0);
    await expect(page.getByTestId("cube-olap")).toHaveCount(0);
  });
});
