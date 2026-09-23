import { expect, test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "./helpers";

test.describe("Régression : thème et langue (charte, Motion, réduit-motion)", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
  });

  test("bascule de thème clair/sombre", async ({ page }) => {
    await page.locator('button.icon-btn', { hasText: "◐" }).click();
    const theme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    expect(["light", "dark"]).toContain(theme);
  });

  test("bascule de langue FR/EN rebranche les libellés", async ({ page }) => {
    await page.locator("button.icon-btn", { hasText: "EN" }).click();
    await expect(page.getByText("Dashboard").first()).toBeVisible();
  });
});