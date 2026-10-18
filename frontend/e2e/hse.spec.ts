import { expect, test } from "@playwright/test";

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
