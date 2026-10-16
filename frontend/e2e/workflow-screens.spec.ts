import { expect, test, type Page } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

/** POST API avec le jeton de la session courante (prépare les données sans passer par l'UI). */
async function api(page: Page, path: string, body: unknown): Promise<{ id: string; [k: string]: unknown }> {
  return page.evaluate(
    async ([p, b]) => {
      const access = JSON.parse(localStorage.getItem("etls.auth") ?? "{}").state?.access;
      const r = await fetch(p as string, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${access}` },
        body: JSON.stringify(b),
      });
      return r.json();
    },
    [path, body],
  );
}

test.describe("Régression : écrans de workflow (ITP, permis, paie)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
  });

  test("ITP : un point d'arrêt ne se lève pas hors ordre, puis dans l'ordre", async ({ page }) => {
    const label = `ITP e2e ${Date.now()}`;
    const itp = await api(page, "/api/qualite/controles/", { type_controle: "itp", point_controle: label, statut: "en_cours" });
    await api(page, "/api/qualite/points-inspection/", { controle: itp.id, ordre: 1, description: "Fit-up e2e", type_point: "arret" });
    await api(page, "/api/qualite/points-inspection/", { controle: itp.id, ordre: 2, description: "Passe de fond e2e", type_point: "arret" });

    await page.goto("/qualite");
    const card = page.locator("article.itp", { hasText: label });
    await expect(card).toBeVisible();
    const p2 = card.locator("li.itp-point", { hasText: "Passe de fond e2e" });
    const p1 = card.locator("li.itp-point", { hasText: "Fit-up e2e" });

    await p2.getByRole("button", { name: "Lever", exact: true }).click();
    await expect(p2.getByRole("alert")).toContainText(/Levez d'abord/);

    await p1.getByRole("button", { name: "Lever", exact: true }).click();
    await expect(p1).toHaveClass(/leve/);
    await p2.getByRole("button", { name: "Lever", exact: true }).click();
    await expect(p2).toHaveClass(/leve/);
  });

  test("permis à chaud : démarrage refusé sans test gaz, accepté après un test conforme", async ({ page }) => {
    const zone = `Zone e2e ${Date.now()}`;
    const permis = await api(page, "/api/hse/permis/", {
      type_permis: "chaud", emplacement: zone, description: "Soudure e2e", date_debut: new Date().toISOString().slice(0, 10),
    });
    expect(permis.id).toBeTruthy();

    await page.goto("/hse");
    const card = page.locator(".card", { hasText: zone });
    await expect(card).toBeVisible();
    await card.getByRole("button", { name: "Valider", exact: true }).click();
    await expect(card.getByRole("button", { name: "Démarrer", exact: true })).toBeVisible();

    await card.getByRole("button", { name: "Démarrer", exact: true }).click();
    await expect(card.getByRole("alert")).toContainText(/Test gaz conforme requis/);

    await card.getByRole("button", { name: "Test gaz", exact: true }).click();
    await card.getByLabel("Mesures (LIE, O2, H2S…)").fill("LIE 0 %");
    await card.getByRole("button", { name: "Enregistrer" }).click();
    await expect(card.getByText("Test gaz conforme")).toBeVisible();

    await card.getByRole("button", { name: "Démarrer", exact: true }).click();
    await expect(card.getByText("Actif", { exact: true }).first()).toBeVisible();
  });

  test("paie : saisie d'un barème de cotisation (taux = donnée)", async ({ page }) => {
    const code = `E2E-${Date.now() % 100000}`;
    await page.goto("/rh-paie");
    await expect(page.getByText("Barèmes de cotisation").first()).toBeVisible();
    await page.getByPlaceholder("Code").fill(code);
    await page.getByPlaceholder("Libellé").fill("Barème e2e");
    await page.getByPlaceholder("Taux (%)").fill("1.5");
    await page.getByLabel("Date d'effet").fill("2026-01-01");
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByRole("cell", { name: new RegExp(code) })).toBeVisible();
  });
});
