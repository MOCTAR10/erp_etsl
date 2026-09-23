import { expect, test } from "@playwright/test";

import { DEMO_USERS, DEMO_PASSWORD, loginAs } from "./helpers";

test.describe("Authentification", () => {
  test("refuse des identifiants invalides", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Adresse e-mail").fill("nobody@etls.local");
    await page.getByLabel("Mot de passe").fill("wrong-password");
    await page.getByRole("button", { name: "Se connecter" }).click();
    await expect(page.getByText("Identifiants incorrects.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("connecte l'admin et atterrit sur le tableau de bord", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Tableau de bord/);
    await expect(page.getByText("ETSL ERP", { exact: true }).first()).toBeVisible();
  });

  test("déconnexion ramène sur /login", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.getByRole("button", { name: "Déconnexion" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});