import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Clôture M7 (2026-10-18) : audits & inspections, DUER, plans d'urgence et exercices.
test.describe("M7 HSE : parcours de clôture", () => {
  test("l'écran HSE expose audits, DUER et plans d'urgence, et permet de planifier un audit", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/hse");
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/HSE/);
    await expect(page.getByText(/Audits & inspections/).first()).toBeVisible();
    await expect(page.getByText(/DUER \(document unique\)/).first()).toBeVisible();
    await expect(page.getByText(/Plans d'urgence & exercices/).first()).toBeVisible();

    const zone = `Atelier E2E ${Date.now()}`;
    await page.getByRole("button", { name: /Planifier un audit/ }).click();
    const form = page.getByRole("form", { name: /Planifier un audit/ });
    await form.getByLabel("Zone").fill(zone);
    await form.getByLabel("Date prévue").fill("2026-12-01");
    await form.locator("button[type=submit]").click();
    await expect(page.getByRole("cell", { name: zone })).toBeVisible();
  });
});

/** Appel API avec le jeton de la session courante (prépare les données sans passer par l'UI). */
async function apiCall(page: Page, path: string, body: unknown): Promise<{ id: string; code: string }> {
  return page.evaluate(
    async ([p, b]) => {
      const access = JSON.parse(localStorage.getItem("etls.auth") ?? "{}").state?.access;
      const r = await fetch(p as string, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${access}` }, body: JSON.stringify(b),
      });
      return r.json();
    },
    [path, body] as const,
  );
}

// Écarts M7 (2026-10-19) : action corrective soldée avant clôture, retour d'expérience, rapport archivé en GED.
test.describe("M7 HSE : cycle d'un presque-accident", () => {
  test("une action est ajoutée puis soldée, la clôture exige le REX et archive le rapport", async ({ page }) => {
    const description = `Bouteille non arrimée e2e ${Date.now()}`;
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/hse");
    await apiCall(page, "/api/hse/incidents/", {
      type_incident: "quasi_accident", gravite: "mineure", date_evenement: new Date().toISOString(), lieu: "Baie 3",
      zone: "atelier", description,
    });
    await page.reload();
    const carte = () => page.locator(".task-card", { hasText: description });
    await expect(carte()).toContainText("Atelier");

    const action = `Arrimer les bouteilles e2e ${Date.now()}`;
    page.once("dialog", (d) => void d.accept(action));
    await carte().getByRole("button", { name: "Ajouter une action" }).click();
    const ligne = page.getByTestId("actions-hse").getByRole("row", { name: new RegExp(action) });
    await expect(ligne).toBeVisible();

    // Clôture refusée tant que l'action n'est pas soldée.
    page.once("dialog", (d) => void d.accept("Chaînes posées"));
    await carte().getByRole("button", { name: "Clôturer" }).click();
    await expect(carte().getByRole("alert")).toContainText("Actions non soldées");

    await ligne.getByRole("button", { name: "Solder" }).click();
    await ligne.getByLabel("Efficacité vérifiée ?").selectOption("true");
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne).toHaveCount(0);

    page.once("dialog", (d) => void d.accept("Chaînes d'arrimage sur tous les râteliers"));
    await carte().getByRole("button", { name: "Clôturer" }).click();
    await expect(carte()).toContainText("Rapport archivé en GED");
  });
});
