import { expect, test as base, type Page } from "@playwright/test";

export const DEMO_PASSWORD = "Etls#Demo2026";

export const DEMO_USERS = {
  admin: "admin@etls.local",
  finance: "finance@etls.local",
  logistique: "logistique@etls.local",
  rh: "rh@etls.local",
  atelier: "atelier@etls.local",
  qaqc: "qaqc@etls.local",
} as const;

/** Connecte un utilisateur démo via l'UI (SPA : écran pilote). */
export async function loginAs(page: Page, email: string, password = DEMO_PASSWORD) {
  // Purge la session persistée (zustand `etls.auth`) AVANT le login : on passe
  // d'abord par une page, on vide le localStorage, puis on recharge /login.
  // Sans cela, un test qui change de rôle (ex. bi) conserverait la session du
  // beforeEach et GuestOnly redirigerait /login vers /.
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
  await page.goto("/login");
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/^http:\/\/[^/]+\/$/, { timeout: 20_000 });
}

export const test = base.extend<{ role: string }>({
  role: ["admin", { option: true }],
});