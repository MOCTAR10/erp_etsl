import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs, ouvrirParametresModule } from "./helpers";

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

/** Appel API avec le jeton de la session courante (prépare les données sans passer par l'UI). */
async function apiCall(page: Page, path: string, body: unknown): Promise<{ id: string; code: string }> {
  return page.evaluate(
    async ([p, b]) => {
      const access = JSON.parse(localStorage.getItem("etls.auth") ?? "{}").state?.access;
      const r = await fetch(p as string, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${access}` }, body: JSON.stringify(b),
      });
      return r.json();
    },
    [path, body] as const,
  );
}

// Écarts M7 (2026-10-19) : action corrective soldée avant clôture, retour d'expérience, rapport archivé en GED.
test.describe("M7 HSE : cycle d'un presque-accident", () => {
  test("une action est ajoutée puis soldée, la clôture exige le REX et archive le rapport", async ({ page }) => {
    const description = `Bouteille non arrimée e2e ${Date.now()}`;
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/hse");
    await apiCall(page, "/api/hse/incidents/", {
      type_incident: "quasi_accident", gravite: "mineure", date_evenement: new Date().toISOString(), lieu: "Baie 3",
      zone: "atelier", description,
    });
    await page.reload();
    const carte = () => page.locator(".task-card", { hasText: description });
    await expect(carte()).toContainText("Atelier");

    const action = `Arrimer les bouteilles e2e ${Date.now()}`;
    page.once("dialog", (d) => void d.accept(action));
    await carte().getByRole("button", { name: "Ajouter une action" }).click();
    const ligne = page.getByTestId("actions-hse").getByRole("row", { name: new RegExp(action) });
    await expect(ligne).toBeVisible();

    // Clôture refusée tant que l'action n'est pas soldée.
    page.once("dialog", (d) => void d.accept("Chaînes posées"));
    await carte().getByRole("button", { name: "Clôturer" }).click();
    await expect(carte().getByRole("alert")).toContainText("Actions non soldées");

    await ligne.getByRole("button", { name: "Solder" }).click();
    await ligne.getByLabel("Efficacité vérifiée ?").selectOption("true");
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne).toHaveCount(0);

    page.once("dialog", (d) => void d.accept("Chaînes d'arrimage sur tous les râteliers"));
    await carte().getByRole("button", { name: "Clôturer" }).click();
    await expect(carte()).toContainText("Rapport archivé en GED");
  });
});

// Écarts M7-C (2026-10-19) : ISO 14001 (consommations → émissions), indicateurs, bilan annuel / revue de direction.
test.describe("M7 HSE : environnement et revue de direction", () => {
  test("un relevé de consommation saisi à l'écran alimente le rapport environnemental", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/hse");
    await expect(page.getByTestId("indicateurs-hse")).toContainText("Taux de formation");
    await expect(page.getByTestId("revues-direction")).toBeVisible();
    const env = page.getByTestId("environnement-hse");
    await env.getByRole("button", { name: /Relevé de consommation/ }).click();
    const form = page.getByRole("form", { name: /Relevé de consommation/ });
    await form.getByLabel("Mois").fill(new Date().toISOString().slice(0, 10));
    await form.getByLabel("Quantité").fill("100");
    await form.getByLabel("Site", { exact: true }).fill(`Base e2e ${Date.now()}`);
    await form.locator("button[type=submit]").click();
    await expect(env.getByRole("row", { name: /Gazole/ })).toBeVisible();
    await expect(env).toContainText("t CO2e");
  });
});

// Écarts M7-D (2026-10-19) : demande de permis à l'écran, coûts HSE lus par le contrôle de gestion.
test.describe("M7 HSE : permis demandé à l'écran", () => {
  test("le chef d'atelier demande un permis, qui apparaît en attente de visa", async ({ page }) => {
    const emplacement = `Rack e2e ${Date.now()}`;
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/hse");
    await page.getByRole("button", { name: /Demander un permis/ }).click();
    const form = page.getByRole("form", { name: /Demander un permis/ });
    await form.getByLabel("Emplacement / zone").fill(emplacement);
    await form.getByLabel("Nature des travaux").fill("Pose de chemin de câbles");
    await form.getByLabel("Début").fill(new Date().toISOString().slice(0, 10));
    await form.locator("button[type=submit]").click();
    await page.getByPlaceholder(/permis/i).first().fill(emplacement);
    const carte = page.locator(".card", { hasText: emplacement });
    await expect(carte).toContainText("Demandé");
    await expect(carte.getByRole("button", { name: "Joindre une photo" })).toBeVisible();
  });

  test("le contrôle de gestion affiche les coûts HSE par centre", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/controle-gestion");
    await expect(page.getByTestId("couts-hse")).toContainText(/HSE/);
  });
});

// Écarts M7 (lot ecarts-m6m7) : check-lists, plans de prévention, prestataires déchets agréés, fiches sécurité, listes.
test.describe("M7 HSE : écarts check-lists, prévention, BSD et fiches sécurité", () => {
  test("les fiches sécurité sont publiées et un prestataire déchets agréé se saisit", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
    await page.goto("/hse");
    await expect(page.getByTestId("fiches-securite")).toContainText("Travaux à chaud");
    await expect(page.getByTestId("checklists-hse")).toBeVisible();
    await expect(page.getByTestId("plans-prevention")).toBeVisible();
    // Listes paramétrables : paramétrage replié en bas de page (B11).
    await ouvrirParametresModule(page);
    await expect(page.getByTestId("listes-hse")).toContainText("Provisoire");
    const bloc = page.getByTestId("bsd-prestataires");
    const nom = `Collecte e2e ${Date.now()}`;
    await bloc.getByRole("button", { name: "Ajouter un prestataire agréé" }).click();
    const form = page.getByRole("form", { name: "Ajouter un prestataire agréé" });
    await form.getByLabel("Raison sociale *", { exact: true }).fill(nom);
    await form.getByLabel("N° d'agrément *", { exact: true }).fill("MIN-ENV-E2E");
    await form.getByLabel("Agrément valable jusqu'au *", { exact: true }).fill("2030-12-31");
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");
    await expect(bloc.getByRole("row", { name: new RegExp(nom) })).toContainText("Agréé");
  });
});
