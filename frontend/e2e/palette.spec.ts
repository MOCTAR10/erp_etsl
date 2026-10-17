import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

test.describe("Régression : palette de commandes (Ctrl K)", () => {
  test("Ctrl+K ouvre la palette, la recherche tolère les accents, Entrée navigue", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/");
    // le raccourci n'est actif qu'une fois le Shell monté (pages en lazy-loading)
    await expect(page.getByRole("button", { name: "Rechercher un module…" })).toBeVisible();
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await page.getByRole("dialog").getByRole("combobox").fill("comptabilite");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/comptabilite$/);
    await expect(dialog).toBeHidden();
  });

  test("Échap ferme la palette", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.getByRole("button", { name: "Rechercher un module…" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("la palette respecte les droits : rh ne trouve pas Comptabilité", async ({ page }) => {
    await loginAs(page, DEMO_USERS.rh);
    await expect(page.getByRole("button", { name: "Rechercher un module…" })).toBeVisible();
    await page.keyboard.press("Control+k");
    await page.getByRole("dialog").getByRole("combobox").fill("comptabilite");
    await expect(page.getByRole("option")).toHaveCount(0);
  });
});
