import { expect, test as base, type Page } from "@playwright/test";

export const DEMO_PASSWORD = "Etls#Demo2026";

export const DEMO_USERS = {
  admin: "admin@etls.local",
  direction: "direction@etls.local",
  finance: "finance@etls.local",
  logistique: "logistique@etls.local",
  rh: "rh@etls.local",
  atelier: "atelier@etls.local",
  qaqc: "qaqc@etls.local",
  salarie: "salarie@etls.local",
} as const;

/**
 * Déplie la section « Paramètres du module » (B11), repliée par défaut en bas des écrans métier : son contenu
 * (référentiels, barèmes, paramètres provisoires…) n'est monté qu'une fois dépliée. Sans effet si elle l'est déjà.
 */
export async function ouvrirParametresModule(page: Page) {
  const toggle = page.getByTestId("module-settings").locator(".ui-modsettings-toggle");
  await toggle.waitFor({ timeout: 20_000 });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
}

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
  // La page d'atterrissement dépend du rôle (`src/lib/landing.ts`) : on vérifie
  // donc que la session est établie — hors /login et shell applicatif monté —
  // et non plus une URL unique. Chaque spec fait son propre `goto()` ensuite.
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 20_000 });
  await expect(page.locator(".sidebar")).toBeVisible({ timeout: 20_000 });
}

export const test = base.extend<{ role: string }>({
  role: ["admin", { option: true }],
});