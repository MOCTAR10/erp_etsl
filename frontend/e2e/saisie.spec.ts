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
    await card.getByRole("button", { name: "Planifier" }).click();
    await expect(page.locator(".task-card", { hasText: label }).getByRole("button", { name: "Planifier" })).toHaveCount(0);
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
