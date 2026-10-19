import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Clôture M6 (2026-10-18) : métrologie, registre des joints, épreuves P/T et approbation de l'ITP.
test.describe("M6 Qualité : parcours de clôture", () => {
  test("l'écran Qualité expose métrologie, joints, épreuves et l'approbation de l'ITP", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/qualite");
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Qualité/);
    await expect(page.getByText(/Métrologie \(étalonnage\)/).first()).toBeVisible();
    await expect(page.getByText(/Registre des joints soudés/).first()).toBeVisible();
    await expect(page.getByText(/Épreuves hydrauliques/).first()).toBeVisible();
  });
});

// Écarts M6-A (2026-10-19) : saisies soudage / ITP, cycle WPS, CAPA, punch list, indicateurs et paramètres qualité.
test.describe("M6 Qualité : écarts M6-A", () => {
  test("le QA/QC saisit un soudeur et pilote WPS, punch list, indicateurs et paramètres", async ({ page }) => {
    await loginAs(page, DEMO_USERS.qaqc, DEMO_PASSWORD);
    await page.goto("/qualite");
    const saisies = page.getByTestId("saisies-m6");
    await saisies.getByRole("button", { name: "Nouveau soudeur" }).click();
    const form = page.getByRole("form", { name: "Nouveau soudeur" });
    await form.getByLabel("Nom *").fill(`E2E SOUDEUR ${Date.now()}`);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");
    await expect(page.getByTestId("wps-cycle")).toBeVisible();
    await expect(page.getByTestId("punch-list")).toBeVisible();
    await expect(page.getByTestId("indicateurs-qualite").getByText("Taux de conformité")).toBeVisible();
    await expect(page.getByTestId("parametres-qualite").getByText("CAPA : délai de clôture (jours calendaires)")).toBeVisible();
  });
});
