import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M11 : seuils de sous-activité et doctrine Mix A/B/C paramétrables par ETSL, valeurs provisoires signalées.
test.describe("M11 Contrôle de gestion : paramètres de pilotage", () => {
  test("un paramètre provisoire est signalé, modifié puis confirmé par la finance", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/controle-gestion");
    const section = page.getByTestId("pilotage-gestion");
    await expect(section.getByTestId("alerte-provisoire-gestion")).toContainText(/provisoire/);
    await expect(section.getByRole("cell", { name: "Mix A", exact: true })).toBeVisible();

    const ligne = section.getByRole("row", { name: /Sous-activité maximale du centre 90/ });
    // Valeur différente de l'actuelle : une valeur inchangée resterait « confirmée » d'une exécution à l'autre.
    const actuelle = /(?<![\d.,])5([.,]00)?\s%/.test(await ligne.innerText()) ? "6" : "5";
    await ligne.getByRole("button", { name: "Modifier" }).click();
    await ligne.getByRole("spinbutton").fill(actuelle);
    await ligne.getByRole("button", { name: "Valider" }).click();
    await expect(ligne).toContainText(new RegExp(`(?<![\\d.,])${actuelle}([.,]00)?\\s%`));

    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();
  });

  test("les marges brute, opérationnelle et nette et l'atterrissage sont affichés", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/controle-gestion");
    const niveaux = page.getByTestId("niveaux-marge");
    await expect(niveaux).toContainText("Marge brute");
    await expect(niveaux).toContainText("Marge opérationnelle");
    await expect(niveaux).toContainText("Marge nette");
    await expect(page.getByTestId("pilotage-gestion")).toContainText("Atterrissage de fin d'exercice");
  });
});

// M11 : budget saisi à l'écran puis double visa DAF + CG par deux personnes distinctes.
test.describe("M11 Contrôle de gestion : saisie budgétaire et double visa", () => {
  test("un budget créé à l'écran n'entre en vigueur qu'avec deux visas de deux personnes", async ({ page }) => {
    const label = `Budget recette ${Date.now()}`;
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/controle-gestion");
    await page.getByTestId("saisie-budgetaire").getByRole("button", { name: "Nouveau budget" }).click();
    const form = page.getByRole("form", { name: "Nouveau budget" });
    await form.getByLabel(/Intitulé/).fill(label);
    await form.getByLabel(/Montant annuel/).fill("1200000");
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByText("Enregistré.")).toBeVisible();

    const carte = () => page.locator(".task-card", { hasText: label });
    await expect(carte()).toContainText("Visa DAF en attente");
    await carte().getByRole("button", { name: "Approuver" }).click();
    await carte().getByLabel("Visa à apposer…").selectOption("daf");
    await carte().getByRole("button", { name: "Confirmer" }).click();
    await expect(carte()).toContainText("Visa DAF posé");
    // La même personne ne peut pas poser aussi le visa CG.
    await carte().getByRole("button", { name: "Approuver" }).click();
    await carte().getByLabel("Visa à apposer…").selectOption("cg");
    await carte().getByRole("button", { name: "Confirmer" }).click();
    await expect(carte().getByRole("alert")).toContainText(/autre personne/);

    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/controle-gestion");
    await expect(carte()).toContainText("Visa DAF posé");
    await carte().getByRole("button", { name: "Approuver" }).click();
    await carte().getByLabel("Visa à apposer…").selectOption("cg");
    await carte().getByRole("button", { name: "Confirmer" }).click();
    // Budget approuvé : plus de visa à poser, la clôture devient possible.
    await expect(carte().getByRole("button", { name: "Clôturer" })).toBeVisible();
    await expect(carte()).not.toContainText("Visa DAF en attente");
  });

  test("la détection des écarts > 10 % répond à l'écran", async ({ page }) => {
    await loginAs(page, DEMO_USERS.finance);
    await page.goto("/controle-gestion");
    await page.getByRole("button", { name: /Détecter les écarts/ }).click();
    await expect(page.getByTestId("saisie-budgetaire").locator("xpath=following-sibling::p").first()).toContainText(/analyse|écart/);
  });
});
