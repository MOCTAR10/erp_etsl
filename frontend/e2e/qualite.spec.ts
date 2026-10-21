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

// Écarts M6-B (2026-10-21) : contrôles mesurés contre des seuils paramétrables, métrologie typée.
test.describe("M6 Qualité : écarts M6-B", () => {
  test("le QA/QC crée un contrôle peinture, saisit une mesure et voit les seuils provisoires", async ({ page }) => {
    await loginAs(page, DEMO_USERS.qaqc, DEMO_PASSWORD);
    await page.goto("/qualite");
    const bloc = page.getByTestId("controles-mesures");
    await bloc.getByRole("button", { name: "Nouveau contrôle mesuré" }).click();
    const form = page.getByRole("form", { name: "Nouveau contrôle mesuré" });
    const point = `E2E PEINTURE ${Date.now()}`;
    await form.getByLabel("Point de contrôle").fill(point);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");
    const ligne = bloc.locator("tr").filter({ hasText: point });
    await ligne.getByLabel("Critère").selectOption({ index: 1 });
    await ligne.getByLabel("Valeur").fill("1");
    await ligne.getByRole("button", { name: "Saisir la mesure" }).click();
    await expect(ligne.getByText(/hors seuil/)).toBeVisible();
    await expect(page.getByTestId("criteres-controle").getByText("Provisoire").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Étiquette" }).first()).toBeVisible();
  });
});

// Écarts M6-C (2026-10-21) : système qualité ISO 9001 (liste maîtresse, processus, audits, compétences, revue de direction).
test.describe("M6 Qualité : écarts M6-C", () => {
  test("le QA/QC crée une procédure, l'approuve et planifie un audit", async ({ page }) => {
    await loginAs(page, DEMO_USERS.qaqc, DEMO_PASSWORD);
    await page.goto("/qualite");
    const docs = page.getByTestId("liste-maitresse");
    await docs.getByRole("button", { name: "Nouveau document qualité" }).click();
    const form = page.getByRole("form", { name: "Nouveau document qualité" });
    const titre = `E2E PROCEDURE ${Date.now()}`;
    await form.getByLabel("Titre *").fill(titre);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");
    const ligne = docs.locator("tr").filter({ hasText: titre });
    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Approuver" }).click();
    await expect(ligne.getByText("En vigueur")).toBeVisible();
    const audits = page.getByTestId("audits-qualite");
    await audits.getByRole("button", { name: "Nouvel audit" }).click();
    const fa = page.getByRole("form", { name: "Nouvel audit" });
    const perimetre = `E2E AUDIT ${Date.now()}`;
    await fa.getByLabel("Périmètre *").fill(perimetre);
    await fa.getByRole("button", { name: "Enregistrer" }).click();
    await expect(audits.locator("tr").filter({ hasText: perimetre }).getByText("Planifié")).toBeVisible();
    await expect(page.getByTestId("competences-qualite")).toBeVisible();
    await expect(page.getByTestId("revue-qualite").getByText("Audits réalisés / planifiés")).toBeVisible();
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
