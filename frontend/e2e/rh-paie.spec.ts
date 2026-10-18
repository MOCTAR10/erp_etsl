import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M9 : barèmes de paie paramétrables, valeurs provisoires signalées jusque sur les bulletins.
test.describe("M9 RH & Paie : paramétrage des barèmes", () => {
  test("un barème provisoire est signalé, puis confirmé par le cercle paie", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await page.goto("/rh-paie");
    await expect(page.getByTestId("alerte-provisoire")).toContainText(/provisoire/);

    const code = `E2E-${Date.now() % 100000}`;
    await page.getByPlaceholder("Code").fill(code);
    await page.getByPlaceholder("Libellé").fill("Barème m9 e2e");
    await page.getByPlaceholder("Taux (%)").fill("1.5");
    await page.getByLabel("Date d'effet").fill("2026-01-01");
    await page.getByRole("button", { name: "Enregistrer" }).click();

    const ligne = page.getByRole("row", { name: new RegExp(code) });
    await expect(ligne.getByText("Provisoire")).toBeVisible();
    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();

    await ligne.getByRole("button", { name: "Historique" }).click();
    await expect(page.getByText(/confirmation/)).toBeVisible();
  });

  test("les paramètres de paie (SMIG, durée légale) sont visibles", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await page.goto("/rh-paie");
    await expect(page.getByText("DUREE_LEGALE_HEBDO")).toBeVisible();
    await expect(page.getByText("SMIG", { exact: true })).toBeVisible();
  });
});

test.describe("M9 : ETSL modifie les taux lui-même", () => {
  test("un taux de cotisation se modifie depuis l'écran et repasse en provisoire", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await page.goto("/rh-paie");
    const ligne = page.getByRole("row", { name: /CNSS-VIEIL-S/ });
    await ligne.getByRole("button", { name: "Modifier" }).click();
    await ligne.getByLabel("Taux (%)").fill("5.5");
    await ligne.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByRole("row", { name: /CNSS-VIEIL-S/ })).toContainText("5.5");
    await expect(page.getByRole("row", { name: /CNSS-VIEIL-S/ })).toContainText("Provisoire");
  });
});

test.describe("M9 : bulletin PDF et virement des salaires", () => {
  test("le bulletin se télécharge en PDF et un compte émetteur se saisit", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await page.goto("/rh-paie");
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "PDF", exact: true }).first().click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.pdf$/);

    await expect(page.getByText("Virement des salaires (CFONB 160)")).toBeVisible();
    const num = String(Date.now() % 100000000000).padStart(11, "0");
    const form = page.locator("form", { has: page.getByPlaceholder("Raison sociale (24 car.)") });
    await form.getByPlaceholder("Raison sociale (24 car.)").fill("ETSL E2E");
    await form.getByPlaceholder("N° d'émetteur (6)").fill("123456");
    await form.getByPlaceholder("Banque (5 ch.)").fill("30001");
    await form.getByPlaceholder("Guichet (5 ch.)").fill("00123");
    await form.getByPlaceholder("N° de compte").fill(num);
    await form.getByPlaceholder("Clé RIB").fill("45");
    await form.getByRole("button", { name: "Ajouter le compte" }).click();
    await expect(page.getByRole("option", { name: new RegExp(num) })).toBeAttached();
  });
});
