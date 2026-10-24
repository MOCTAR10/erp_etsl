import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M10 : paramètres de clôture/lettrage modifiables par ETSL, valeurs provisoires signalées.
test.describe("M10 Comptabilité : paramètres de lettrage", () => {
  test("un paramètre provisoire est signalé, modifié puis confirmé par la finance", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/comptabilite");
    await expect(page.getByTestId("alerte-provisoire-compta")).toContainText(/provisoire/);
    // Paramètres repliés dans un panneau compact (B-05) : on les affiche avant de les modifier.
    await page.getByTestId("parametres-compta").getByRole("button", { name: "Afficher", exact: true }).click();

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

const MT940 = [
  ":20:E2E", ":25:00099999999", ":28C:1/1",
  ":60F:C260601XAF1000000,00",
  ":61:2606020602C500000,00NTRFNONREF//E2E1", ":86:VIREMENT CLIENT E2E",
  ":62F:C260630XAF1500000,00",
].join("\n");

// M10 : import d'un relevé MT940 (gabarit standard) et rapprochement automatique.
test.describe("M10 Comptabilité : relevé bancaire", () => {
  test("un relevé MT940 s'importe, un second import du même fichier est refusé, le rapprochement liste les écarts", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/comptabilite");

    const compte = page.getByLabel("Compte du relevé", { exact: true });
    await expect.poll(async () => await compte.locator("option").count()).toBeGreaterThan(1);
    await compte.selectOption({ index: 1 });
    // Fichier unique par exécution (l'empreinte du fichier interdit le double import).
    const contenu = MT940.replace("E2E1", `E${Date.now() % 100000}`);
    await page.getByLabel("Fichier de relevé").setInputFiles({ name: "releve.sta", mimeType: "text/plain", buffer: Buffer.from(contenu) });
    await page.getByRole("button", { name: "Importer le relevé" }).click();
    await expect(page.getByTestId("import-resultat")).toContainText("1 ligne(s) importée(s)");

    await page.getByLabel("Fichier de relevé").setInputFiles({ name: "releve.sta", mimeType: "text/plain", buffer: Buffer.from(contenu) });
    await page.getByRole("button", { name: "Importer le relevé" }).click();
    await expect(page.getByRole("alert").first()).toContainText(/déjà été importé/);

    await page.getByRole("button", { name: "Rapprocher automatiquement" }).click();
    await expect(page.getByTestId("rapprochement-resultat")).toContainText("rapprochée");
  });
});

// M10 : le modèle de facture client est une donnée ETSL, provisoire jusqu'à confirmation.
test.describe("M10 Comptabilité : facturation client", () => {
  test("le modèle de facture provisoire est signalé, modifié puis confirmé", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/comptabilite");
    await page.getByRole("heading", { name: /Modèle de facture/ }).locator("xpath=following-sibling::button[1]").click();
    await page.getByLabel("En-tête").fill(`ETSL e2e ${Date.now() % 100000}`);
    await page.getByRole("button", { name: "Valider" }).click();
    await expect(page.getByTestId("alerte-modele-provisoire")).toContainText(/provisoire/);

    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: "Confirmer le modèle" }).click();
    await expect(page.getByTestId("alerte-modele-provisoire")).toHaveCount(0);
  });
});

// M10 : clôture mensuelle — les contrôles de pré-clôture s'affichent pour une période ouverte.
test.describe("M10 Comptabilité : clôture mensuelle", () => {
  test("les contrôles de pré-clôture sont listés pour la période choisie", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/comptabilite");
    const periode = page.getByLabel("Période à clôturer");
    await expect.poll(async () => await periode.locator("option").count()).toBeGreaterThan(1);
    await periode.selectOption({ index: 1 });
    const tableau = page.getByTestId("cloture-controles");
    await expect(tableau).toContainText("Écritures en brouillon");
    await expect(tableau).toContainText("Bulletins de paie validés non comptabilisés");
  });
});
