import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

// Clôture M5 (2026-10-17) : valorisation mensuelle publiée à M11 et inventaires tournants planifiés.
test.describe("M5 Stocks : parcours de clôture", () => {
  test("la valorisation mensuelle se fige depuis l'écran Stocks", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/stocks");
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Stocks/);
    await expect(page.getByText(/Valorisation mensuelle/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Figer le mois" })).toBeVisible();
  });
});

/** Appel API avec le jeton de la session courante (prépare les données sans passer par l'UI). */
async function apiCall(page: Page, path: string, body?: unknown): Promise<any> {
  return page.evaluate(
    async ([p, b]) => {
      const access = JSON.parse(localStorage.getItem("etls.auth") ?? "{}").state?.access;
      const r = await fetch(p as string, {
        method: b === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${access}` },
        body: b === undefined ? undefined : JSON.stringify(b),
      });
      return r.json();
    },
    [path, body] as const,
  );
}

// Écarts M5 (2026-10-19) : quarantaine motivée puis levée, validation QA-QC d'un certificat, traçabilité d'un lot.
test.describe("M5 Stocks : quarantaine, certificats et traçabilité", () => {
  test("un lot est mis en quarantaine puis libéré, son certificat validé et sa chaîne tracée", async ({ page }) => {
    const numero = `HEAT-e2e-${Date.now()}`;
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/stocks");
    const article = (await apiCall(page, "/api/referentiels/articles/?search=TUBE-01")).results[0];
    const depot = (await apiCall(page, "/api/stocks/depots/")).results[0];
    const lot = await apiCall(page, "/api/stocks/lots/", {
      article: article.id, numero_lot: numero, numero_coulee: "C-E2E", date_reception: new Date().toISOString().slice(0, 10),
      quantite_initiale: "20",
    });
    await apiCall(page, "/api/stocks/mouvements/", {
      type_mouvement: "reception", article: article.id, quantite: "20", prix_unitaire: "100", destination: depot.id, lot: lot.id,
      date: new Date().toISOString().slice(0, 10),
    });
    await apiCall(page, "/api/stocks/certificats/", { lot: lot.id, type: "mtc", numero_certificat: `MTC-${numero}` });
    await page.reload();

    const carte = () => page.locator(".task-card", { hasText: numero });
    page.once("dialog", (d) => void d.accept("Doute e2e sur la coulée"));
    await carte().getByRole("button", { name: "Mettre en quarantaine" }).click();
    await expect(carte()).toContainText("Quarantaine : Doute e2e sur la coulée");
    page.once("dialog", (d) => void d.accept());
    await carte().getByRole("button", { name: "Lever la quarantaine" }).click();
    await expect(carte()).not.toContainText("Quarantaine");
    await expect(carte()).toContainText("Disponible");

    const certificat = page.getByRole("row", { name: new RegExp(`MTC-${numero}`) });
    await expect(certificat).toContainText("À valider");
    await certificat.getByRole("button", { name: "Valider" }).click();
    await certificat.getByLabel("Résultat de la validation…").selectOption("true");
    await certificat.getByRole("button", { name: "Confirmer" }).click();
    await expect(certificat).not.toContainText("À valider");

    const trace = page.getByTestId("tracabilite-lot");
    await trace.getByLabel("Lot").selectOption({ label: `${lot.code} · ${numero} · C-E2E` });
    await expect(trace.getByRole("listitem").first()).toContainText("Réception");
  });
});
