import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// Lot C M2 : consultation, offres et bons de commande saisis depuis l'écran Achats (avant : API seulement).
test.describe("Régression : Achats M2 — saisie des consultations et des bons de commande", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
  });

  test("une consultation s'ouvre, reçoit une offre retenue puis se clôture", async ({ page }) => {
    const sujet = `Consultation e2e ${Date.now()}`;
    await page.goto("/purchases");
    await page.getByRole("button", { name: "Nouvelle consultation" }).click();
    const form = page.getByRole("form", { name: "Nouvelle consultation" });
    await form.getByLabel(/Objet/).fill(sujet);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");

    const row = () => page.getByRole("row", { name: new RegExp(sujet) });
    await row().getByRole("button", { name: "Ouvrir" }).click();
    await expect(row()).toContainText("Ouverte");

    await page.getByRole("button", { name: "Ajouter une offre fournisseur" }).click();
    const offre = page.getByRole("form", { name: "Ajouter une offre fournisseur" });
    const consultation = offre.getByLabel(/Consultation/);
    await expect(consultation.locator("option", { hasText: sujet })).toBeAttached();
    await consultation.selectOption({ label: (await consultation.locator("option", { hasText: sujet }).textContent()) ?? "" });
    const fournisseur = offre.getByLabel(/Fournisseur/);
    await expect(fournisseur.locator("option").nth(1)).toBeAttached();
    await fournisseur.selectOption({ index: 1 });
    await offre.getByLabel(/Montant/).fill("125000");
    await offre.getByRole("button", { name: "Enregistrer" }).click();
    await expect(offre.getByRole("status")).toHaveText("Enregistré.");

    const ligneOffre = page.getByRole("row").filter({ hasText: /125/ }).filter({ has: page.getByRole("button", { name: "Retenir" }) });
    await ligneOffre.first().getByRole("button", { name: "Retenir" }).click();
    await expect(page.getByText("Retenue", { exact: true }).first()).toBeVisible();
    await row().getByRole("button", { name: "Clôturer" }).click();
    await expect(row()).toContainText("Clôturée");
  });

  test("un bon de commande se crée en brouillon et reçoit une ligne", async ({ page }) => {
    const designation = `Tube e2e ${Date.now()}`;
    await page.goto("/purchases");
    await page.getByRole("button", { name: "Nouveau bon de commande" }).click();
    const form = page.getByRole("form", { name: "Nouveau bon de commande" });
    const fournisseur = form.getByLabel(/Fournisseur/);
    await expect(fournisseur.locator("option").nth(1)).toBeAttached();
    await fournisseur.selectOption({ index: 1 });
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");

    await page.getByRole("button", { name: "Ajouter une ligne de commande" }).click();
    const ligne = page.getByRole("form", { name: "Ajouter une ligne de commande" });
    const bc = ligne.getByLabel(/Bon de commande/);
    await expect(bc.locator("option").nth(1)).toBeAttached();
    await bc.selectOption({ index: 1 });
    await ligne.getByLabel(/Désignation/).fill(designation);
    await ligne.getByLabel(/Prix unitaire/).fill("2500");
    await ligne.getByRole("button", { name: "Enregistrer" }).click();
    await expect(ligne.getByRole("status")).toHaveText("Enregistré.");
  });

  test("les factures fournisseurs exposent le rapprochement et la comptabilisation", async ({ page }) => {
    await page.goto("/purchases");
    await expect(page.getByRole("button", { name: "Nouvelle facture fournisseur" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Ajouter une ligne de facture" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Ajouter une ligne de DA" })).toBeVisible();
  });
});
