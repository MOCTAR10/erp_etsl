import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

/** Compte les pointages visibles côté serveur pour le libellé d'opérateur donné (token de la session). */
async function pointagesDe(page: import("@playwright/test").Page, operateur: string): Promise<number> {
  return page.evaluate(async (name) => {
    const access = JSON.parse(localStorage.getItem("etls.auth") ?? "{}").state?.access;
    const r = await fetch("/api/operations/pointages/", { headers: { Authorization: `Bearer ${access}` } });
    const data = await r.json();
    return (data.results as { worker_name: string }[]).filter((p) => p.worker_name === name).length;
  }, operateur);
}

test.describe("Régression : saisie terrain hors-ligne (CL-OM-08)", () => {
  test("une saisie faite sans réseau est conservée puis envoyée UNE fois au retour du réseau", async ({
    page,
    context,
  }) => {
    const operateur = `Offline-${Date.now()}`;
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/terrain");
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(/Saisie terrain/);
    await expect(page.getByText("En ligne", { exact: true })).toBeVisible();

    // la liste des ordres de fabrication est chargée (copie locale pour la saisie hors-ligne)
    const ordre = page.locator("select").first();
    await expect(ordre.locator("option")).not.toHaveCount(1);

    await context.setOffline(true);
    await expect(page.getByText("Hors-ligne", { exact: true })).toBeVisible();

    await ordre.selectOption({ index: 1 });
    await page.getByLabel("Opérateur").fill(operateur);
    await page.getByLabel("Heures").fill("7");
    await page.getByRole("button", { name: "Enregistrer" }).click();

    await expect(page.getByText(/Enregistré sur l'appareil/)).toBeVisible();
    await expect(page.getByText("1 saisie(s) en attente d'envoi")).toBeVisible();

    // le retour du réseau déclenche la synchronisation automatique
    await context.setOffline(false);
    await expect(page.getByText("Tout est synchronisé")).toBeVisible({ timeout: 20_000 });
    expect(await pointagesDe(page, operateur)).toBe(1);

    // une 2e synchronisation manuelle ne duplique rien
    await page.reload();
    await expect(page.getByText("Tout est synchronisé")).toBeVisible();
    expect(await pointagesDe(page, operateur)).toBe(1);
  });

  test("une saisie refusée par le serveur est signalée en échec sans bloquer l'appareil", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/terrain");
    const ordre = page.locator("select").first();
    await expect(ordre.locator("option")).not.toHaveCount(1);
    await ordre.selectOption({ index: 1 });
    await page.getByLabel("Opérateur").fill("Refus");
    await page.getByLabel("Heures").fill("30"); // > 24 h : refusé par le serveur
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByText("Échec", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/24 h/)).toBeVisible();
  });
});
