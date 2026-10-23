import { expect, test, type Page } from "@playwright/test";

/**
 * 10 écrans de référence × 3 projets (clair, sombre, mobile : voir playwright.visuel.config.ts).
 * Capture de la fenêtre visible (pas la page entière) : la mise en page « au-dessus de la ligne de flottaison »
 * est ce que l'on juge, et la longueur des listes varie avec les données de démo.
 */
const ECRANS: { nom: string; route: string; titre: RegExp }[] = [
  { nom: "connexion", route: "/login", titre: /ETSL ERP/ },
  { nom: "tableau-de-bord", route: "/", titre: /Tableau de bord/ },
  { nom: "direction", route: "/direction", titre: /Direction \/ BI/ },
  { nom: "validations", route: "/kanban", titre: /./ },
  { nom: "achats", route: "/purchases", titre: /Achats/ },
  { nom: "operations", route: "/operations", titre: /Opérations/ },
  { nom: "stocks", route: "/stocks", titre: /Stocks/ },
  { nom: "hse", route: "/hse", titre: /HSE/ },
  { nom: "comptabilite", route: "/comptabilite", titre: /Comptabilité/ },
  { nom: "documents", route: "/documents", titre: /Documents/ },
];

/**
 * Zones volatiles masquées (aplat) : horodatages et éléments animés en continu. Une page peut en déclarer
 * d'autres avec l'attribut `data-visuel="volatil"` (convention, voir DESIGN_SYSTEM.md).
 */
const VOLATILS = ['[data-visuel="volatil"]', "time", ".ui-toast", "[data-sonner-toaster]"];

/** Thème et langue posés avant le chargement de l'application (mêmes clés que main.tsx / i18n). */
async function preparer(page: Page, sombre: boolean) {
  await page.addInitScript((theme) => {
    localStorage.setItem("etls.theme", theme);
    localStorage.setItem("etls.lang", "fr");
  }, sombre ? "dark" : "light");
}

/** Attend un écran stable : réseau calme, squelettes disparus, polices chargées, animations d'entrée finies. */
async function stabiliser(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 20_000 }).catch(() => {});
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600);
}

for (const { nom, route, titre } of ECRANS) {
  test(`${nom} (${route})`, async ({ page, context }, info) => {
    if (route === "/login") await context.clearCookies();
    await preparer(page, info.project.name === "sombre");
    if (route === "/login") {
      // Écran public : session vidée pour ne pas être redirigé vers l'accueil.
      await page.goto("/login");
      await page.evaluate(() => localStorage.removeItem("etls.auth"));
      await page.reload();
    } else {
      await page.goto(route);
      await expect(page.locator(".sidebar, .nav-toggle").first()).toBeAttached();
    }
    await expect(page.getByText(titre).first()).toBeVisible();
    await stabiliser(page);
    await expect(page).toHaveScreenshot(`${nom}.png`, {
      mask: VOLATILS.map((s) => page.locator(s)),
    });
  });
}
