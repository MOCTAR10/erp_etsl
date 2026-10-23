import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// Jeu de démonstration « parcours » (seed_all_demo, lots A-D) : ce que chaque fonction voit à l'écran une fois le
// parcours rejoué. Lecture seule — aucun test ne modifie les données du parcours, l'ordre d'exécution est indifférent.
const AFFAIRE_CHANTIER = "Parcours demo - Montage tuyauterie chantier";
const AFFAIRE_GR = "Parcours demo - Prestation GLOBAL RENTAL";

test.describe("Parcours démo : finance", () => {
  test("la facture émise de la situation est lettrée au 411 avec son encaissement", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/comptabilite");

    await page.getByPlaceholder("Rechercher une facture (code, objet)…").fill("Situation n1 (demo)");
    const facture = page.getByRole("row").filter({ has: page.getByText(/^FAC\d+$/) }).filter({ hasText: "Émise" });
    await expect(facture).toHaveCount(1);
    // Pièce de vente générée à l'émission (411 · 706 · 443) : c'est elle qu'on retrouve dans le lettrage.
    const piece = (await facture.locator(".muted").first().innerText()).replace("·", "").trim();
    expect(piece).toMatch(/^\S+\d+$/);

    const compte = page.getByLabel("Compte lettrable");
    await expect.poll(async () => await compte.locator("option", { hasText: /^411000 / }).count()).toBe(1);
    const valeur = await compte.locator("option", { hasText: /^411000 / }).getAttribute("value");
    await compte.selectOption(valeur!);
    const lettrage = page.getByRole("row").filter({ has: page.getByText(/^LET\d+$/) }).filter({ hasText: piece });
    await expect(lettrage).toHaveCount(1);
    await expect(lettrage).toContainText("Manuel · 2 ligne(s)");
    await expect(lettrage).toContainText("Actif");
  });
});

test.describe("Parcours démo : direction", () => {
  test("les contrats du parcours sont actifs et le contrat chantier porte son avenant", async ({ page }) => {
    await loginAs(page, DEMO_USERS.direction);
    await page.goto("/pipeline");

    await page.getByPlaceholder("Rechercher un contrat (code, client, affaire)…").fill("Parcours demo");
    const contrats = page.getByRole("table", { name: "Contrats (CLM)" });
    const chantier = contrats.getByRole("row").filter({ hasText: AFFAIRE_CHANTIER });
    const gr = contrats.getByRole("row").filter({ hasText: AFFAIRE_GR });
    await expect(chantier).toHaveCount(1);
    await expect(gr).toHaveCount(1);
    await expect(chantier).toContainText("Actif");
    await expect(gr).toContainText("Actif");
    // Colonne « Avenants » (5e cellule : profil sous le code, client et affaire regroupés) : l'avenant n°1 signé est
    // compté sur le contrat chantier, aucun sur le contrat GR.
    await expect(chantier.getByRole("cell").nth(4)).toHaveText("1");
    await expect(gr.getByRole("cell").nth(4)).toHaveText("0");
  });

  test("le dossier GLOBAL RENTAL du parcours est ouvert et imputé au 618", async ({ page }) => {
    await loginAs(page, DEMO_USERS.direction);
    await page.goto("/juridique");

    await page.getByPlaceholder("Rechercher un dossier Global Rental (code, contrat)…").fill("intra-groupe");
    const dossier = page.getByRole("row").filter({ hasText: "Location d'équipement intra-groupe" });
    await expect(dossier).toHaveCount(1);
    await expect(dossier).toContainText("Ouvert");
    await expect(dossier).toContainText("618");
  });

  test("le budget de l'affaire chantier est approuvé et ses écarts attendent une analyse", async ({ page }) => {
    await loginAs(page, DEMO_USERS.direction);
    await page.goto("/controle-gestion");

    const budget = page.locator(".task-card", { hasText: AFFAIRE_CHANTIER });
    await expect(budget).toHaveCount(1);
    await expect(budget).toContainText("Budget produits");
    // Approuvé (double visa posé par le seed) : seule la clôture reste proposée.
    await expect(budget.getByRole("button", { name: "Clôturer" })).toBeVisible();

    const ecarts = page.locator(".card:not(:has(.card))", { hasText: AFFAIRE_CHANTIER }).filter({ hasText: "analyse attendue avant le" });
    await expect(ecarts.first()).toBeVisible();
    await expect(ecarts.first()).toContainText(/-\d+(\.\d+)? %/);
  });
});
