import { expect, test, type Page } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

/** Appel API avec le jeton de la session courante (prépare les données sans passer par l'UI). */
async function api<T = { id: string; [k: string]: unknown }>(page: Page, method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ([m, p, b]) => {
      const access = JSON.parse(localStorage.getItem("etls.auth") ?? "{}").state?.access;
      const r = await fetch(p as string, {
        method: m as string,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${access}` },
        body: b === undefined ? undefined : JSON.stringify(b),
      });
      return r.json();
    },
    [method, path, body],
  );
}

// Plafond de 20 lignes levé : une liste de plus de 20 enregistrements reste accessible (page 2) et se filtre.
test.describe("Listes : pagination et recherche (inventaires de /stocks)", () => {
  let dernierCode = "";

  test.beforeEach(async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    const depots = await api<{ results: { id: string }[] }>(page, "GET", "/api/stocks/depots/?page_size=1");
    const deja = await api<{ count: number }>(page, "GET", "/api/stocks/inventaires/?page_size=1");
    for (let i = deja.count; i < 25; i++) {
      const inv = await api<{ code: string }>(page, "POST", "/api/stocks/inventaires/", {
        depot: depots.results[0].id,
        date: "2026-10-01",
      });
      dernierCode = inv.code;
    }
    if (!dernierCode) {
      const liste = await api<{ results: { code: string }[] }>(page, "GET", "/api/stocks/inventaires/?page_size=1");
      dernierCode = liste.results[0].code;
    }
  });

  test("au-delà de 20 lignes, la page 2 est accessible", async ({ page }) => {
    await page.goto("/stocks");
    const section = page.locator(".card", { has: page.locator(".card-title", { hasText: /^Inventaires$/ }) });
    await expect(section.locator("tbody tr")).toHaveCount(20);
    const pager = section.getByRole("navigation", { name: "Pagination" });
    await expect(pager.getByText(/^Page 1 \/ \d+$/)).toBeVisible();
    await pager.getByRole("button", { name: "Page suivante" }).click();
    await expect(pager.getByText(/^Page 2 \/ \d+$/)).toBeVisible();
    const lignes = await section.locator("tbody tr").count();
    expect(lignes).toBeGreaterThan(0);
    expect(lignes).toBeLessThanOrEqual(20);
  });

  test("la recherche filtre la liste côté serveur", async ({ page }) => {
    await page.goto("/stocks");
    const section = page.locator(".card", { has: page.locator(".card-title", { hasText: /^Inventaires$/ }) });
    await expect(section.locator("tbody tr")).toHaveCount(20);
    await section.getByRole("searchbox").fill(dernierCode);
    await expect(section.locator("tbody tr")).toHaveCount(1);
    await expect(section.locator("tbody tr").first()).toContainText(dernierCode);
    await section.getByRole("searchbox").fill("");
    await expect(section.locator("tbody tr")).toHaveCount(20);
  });
});
