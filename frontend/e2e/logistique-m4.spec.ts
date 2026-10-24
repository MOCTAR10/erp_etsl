import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs, ouvrirParametresModule } from "./helpers";

// M4 : paramètres de la formule glissante et de la valorisation GR paramétrables par ETSL, valeurs provisoires
// signalées ; coût GR du mois ventilé par affaire (flux compteurs -> M11, compte 618 isolé).
test.describe("M4 Logistique : paramètres GR et coût par affaire", () => {
  test("un paramètre provisoire est signalé, modifié puis confirmé", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/logistique");
    await ouvrirParametresModule(page);
    const section = page.getByTestId("parametres-logistique");
    await expect(section.getByTestId("alerte-provisoire-logistique")).toContainText(/provisoire/);
    // Paramètres repliés dans un panneau compact (B-05) : on les affiche avant de les modifier.
    await section.getByRole("button", { name: "Afficher", exact: true }).click();

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
    await expect(page.getByText("Coût GLOBAL RENTAL par affaire", { exact: false }).first()).toBeVisible();
    await expect(section).toContainText("(618)");
    await expect(section.getByLabel("Mois")).toBeVisible();
  });
});

// M4 : grille tarifaire GLOBAL RENTAL saisie à l'écran — versions datées, jamais modifiées, supprimables tant
// qu'aucune location ne les utilise ; tarifs masqués hors cercle des montants (RF-59).
test.describe("M4 Logistique : grille tarifaire GR", () => {
  test("une version de tarif est créée à l'écran, montant masqué pour la logistique, puis supprimée", async ({ page }) => {
    // Date d'effet unique par exécution (unicité partenaire / cible / périodicité / date d'effet).
    const effet = new Date(Date.UTC(2040, 0, 1) + (Date.now() % 20000) * 86_400_000).toISOString().slice(0, 10);
    await loginAs(page, DEMO_USERS.logistique);
    await page.goto("/logistique");
    // Grille tarifaire : paramétrage replié en bas de page (B11).
    await ouvrirParametresModule(page);
    const section = page.getByTestId("tarifs-gr");
    await section.getByRole("button", { name: "Nouvelle version de tarif" }).click();
    const form = page.getByRole("form", { name: "Nouvelle version de tarif" });
    const partenaire = form.getByLabel(/Partenaire GR/);
    await expect.poll(async () => await partenaire.locator("option").count()).toBeGreaterThan(1);
    await partenaire.selectOption({ index: 1 });
    await form.getByLabel(/Catégorie/).selectOption("atelier");
    await form.getByLabel(/Périodicité/).selectOption("forfait");
    await form.getByLabel(/Tarif unitaire/).fill("250000");
    await form.getByLabel(/Date d'effet/).fill(effet);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByText("Enregistré.")).toBeVisible();

    const ligne = section.locator("tr", { has: page.locator(`time[datetime="${effet}"]`) });
    await expect(ligne).toHaveCount(1);
    await expect(ligne).toContainText("Matériel d'atelier");
    await expect(ligne).toContainText("Forfait");
    await expect(ligne).toContainText(/v\d+/);
    await expect(ligne).toContainText("••••••");

    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Supprimer" }).click();
    await expect(ligne).toHaveCount(0);
  });
});
