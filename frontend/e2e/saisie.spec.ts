import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// Saisie depuis les écrans métier (QuickForm) : création réelle via l'API, visible aussitôt dans la vue.
test.describe("Régression : saisie depuis l'interface", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
  });

  test("Maintenance : un ordre de travail créé apparaît dans le kanban, puis se planifie", async ({ page }) => {
    const label = `Fuite e2e ${Date.now()}`;
    await page.goto("/maintenance");
    await page.getByRole("button", { name: "Nouvel ordre de travail" }).click();
    const form = page.getByRole("form", { name: "Nouvel ordre de travail" });
    const equipement = form.getByLabel(/Équipement/);
    await expect(equipement.locator("option").nth(1)).toBeAttached();
    await equipement.selectOption({ index: 1 });
    await form.getByLabel(/Description de l'intervention/).fill(label);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");

    const card = page.locator(".task-card", { hasText: label });
    await expect(card).toBeVisible();
    // Carte sobre : action principale en bouton, les autres dans le menu « ⋯ ».
    await card.getByRole("button", { name: "Plus d'actions" }).click();
    await page.getByRole("menuitem", { name: "Planifier" }).click();
    await expect(page.locator(".task-card", { hasText: label }).getByRole("button", { name: "Démarrer" })).toBeVisible();
  });

  test("Achats : une demande d'achat se crée, se soumet puis s'approuve", async ({ page }) => {
    const label = `DA e2e ${Date.now()}`;
    await page.goto("/purchases");
    await page.getByRole("button", { name: "Nouvelle demande d'achat" }).click();
    const form = page.getByRole("form", { name: "Nouvelle demande d'achat" });
    await form.getByLabel(/Objet/).fill(label);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");

    const row = () => page.getByRole("row", { name: new RegExp(label) });
    await row().getByRole("button", { name: "Soumettre" }).click();
    await expect(row()).toContainText("Soumise");
    await row().getByRole("button", { name: "Valider" }).click();
    await expect(row()).toContainText("Approuvée");
  });

  test("Qualité : une NC se signale, reçoit un traitement choisi puis se clôture", async ({ page }) => {
    const label = `NC e2e ${Date.now()}`;
    await page.goto("/qualite");
    await page.getByRole("button", { name: "Signaler une non-conformité" }).click();
    const form = page.getByRole("form", { name: "Signaler une non-conformité" });
    await form.getByLabel(/Description de l'écart/).fill(label);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");

    const card = () => page.locator(".task-card", { hasText: label });
    await card().getByRole("button", { name: "Décider du traitement" }).click();
    await card().getByLabel("Traitement…").selectOption("reprise");
    await card().getByRole("button", { name: "Confirmer" }).click();
    page.once("dialog", (d) => void d.accept());
    await card().getByRole("button", { name: "Clôturer" }).click();
    await expect(card().getByRole("button", { name: "Clôturer" })).toHaveCount(0);
  });

  test("Comptabilité : un montant négatif est refusé avec le message du serveur", async ({ page }) => {
    await page.goto("/comptabilite");
    await page.getByRole("button", { name: "Nouveau paiement" }).click();
    const form = page.getByRole("form", { name: "Nouveau paiement" });
    // Contourne le min HTML pour vérifier la validation serveur (montant strictement positif).
    await form.getByLabel(/Montant/).evaluate((el) => el.removeAttribute("min"));
    await form.getByLabel(/Montant/).fill("-5");
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("alert")).toContainText("strictement positif");
  });
});
