import { expect, test } from "@playwright/test";

import { DEMO_USERS, loginAs } from "./helpers";

// M8 : fiabilité du parc (MTBF / MTTR / disponibilité) à paramètres provisoires, pièces de rechange sorties du
// stock M5 et liées à l'OT, réappro sous seuil, coût de maintenance par machine publié à M11.
test.describe("M8 Maintenance : fiabilité, pièces de rechange, coût vers M11", () => {
  test("la fiabilité est publiée avec ses paramètres provisoires, modifiés puis confirmés", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/maintenance");
    const fiabilite = page.getByTestId("fiabilite-parc");
    await expect(fiabilite).toContainText("MTBF");
    await expect(fiabilite.getByTestId("alerte-provisoire-maintenance")).toContainText(/provisoire/);

    const section = page.getByTestId("parametres-maintenance");
    await expect(section.getByTestId("alerte-provisoire-parametres-m8")).toContainText(/provisoire/);
    const ligne = section.getByRole("row", { name: /heures de service théoriques/ });
    // Valeur différente de l'actuelle : une valeur inchangée resterait « confirmée » d'une exécution à l'autre.
    const actuelle = /(?<![\d.])24(\.00)? heures/.test(await ligne.innerText()) ? "20" : "24";
    await ligne.getByRole("button", { name: "Modifier" }).click();
    await ligne.getByRole("spinbutton").fill(actuelle);
    await ligne.getByRole("button", { name: "Valider" }).click();
    await expect(ligne).toContainText(new RegExp(`(?<![\\d.])${actuelle}(\\.00)? heures`));

    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Confirmer" }).click();
    await expect(ligne.getByText("Confirmé")).toBeVisible();
  });

  test("une pièce sort du stock pour un OT puis le réappro propose une demande d'achat", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/maintenance");
    const section = page.getByTestId("pieces-rechange");
    await section.getByLabel("OT", { exact: true }).selectOption({ index: 1 });
    await section.getByLabel("Pièce", { exact: true }).selectOption({ label: "PR-JOINT-VERIN — Joint de verin hydraulique" });
    await section.getByLabel("Dépôt", { exact: true }).selectOption({ label: "DEP-PIECES — Magasin pieces de rechange" });
    await section.getByLabel("Quantité", { exact: true }).fill("1");
    await section.getByRole("button", { name: "Sortir la pièce" }).click();
    await expect(section.getByTestId("pieces-info")).toContainText("Pièce sortie du stock");
    await expect(section.getByTestId("pieces-ot")).toContainText("PR-JOINT-VERIN");

    const reappro = section.getByTestId("reappro-pieces");
    await expect(reappro).toContainText("PR-JOINT-VERIN");
    await reappro.getByRole("button", { name: "Générer la demande d'achat" }).click();
    await expect(section.getByTestId("pieces-info")).toContainText(/Demande d'achat|Aucune nouvelle ligne/);
  });

  test("le coût de maintenance du mois est publié à M11 avec le compte 618 isolé", async ({ page }) => {
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/controle-gestion");
    const section = page.getByTestId("maintenance-couts");
    await expect(page.getByText("Coût de maintenance par machine", { exact: false }).first()).toBeVisible();
    await expect(section).toContainText("(618)");
    await expect(section.getByLabel("Mois")).toBeVisible();
  });
});

// Écarts M8 (2026-10-19) : plans préventifs et calendrier saisis à l'écran, qualification d'une demande et
// historique horodaté des statuts de l'OT.
const isoLocal = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);

test.describe("M8 Maintenance : plans préventifs, qualification et historique", () => {
  test("un plan préventif saisi à l'écran apparaît au calendrier du mois, un autre en pré-alerte", async ({ page }) => {
    const suffixe = Date.now();
    const jour = 24 * 3600_000;
    const aujourdhui = isoLocal(new Date());
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/maintenance");
    const section = page.getByTestId("plans-preventifs");

    const plans = section.getByRole("table", { name: "Plans préventifs et calendrier (M8.2)" });
    const form = page.getByRole("form", { name: "Nouveau plan préventif" });
    await section.getByRole("button", { name: "Nouveau plan préventif" }).click();
    const saisir = async (libelle: string, periodicite: string, derniere: string) => {
      const equipement = form.getByLabel(/Équipement/);
      await expect(equipement.locator("option").nth(1)).toBeAttached();
      await equipement.selectOption({ index: 1 });
      await form.getByLabel(/Intervention/).fill(libelle);
      await form.getByLabel(/Périodicité/).fill(periodicite);
      await form.getByLabel(/Dernière exécution/).fill(derniere);
      await form.getByRole("button", { name: "Enregistrer" }).click();
      await expect(form.getByRole("status")).toHaveText("Enregistré.");
    };

    // Échu aujourd'hui : visible au calendrier du mois courant.
    const echu = `Graissage e2e ${suffixe}`;
    await saisir(echu, "10", isoLocal(new Date(Date.now() - 10 * jour)));
    await expect(plans.getByRole("row", { name: new RegExp(echu) })).toContainText("Échu");
    const calendrier = section.getByTestId("calendrier-preventif");
    await expect(calendrier.locator("tr", { hasText: echu }).locator(`time[datetime="${aujourdhui}"]`)).toBeVisible();

    // Échéance dans 3 jours : pré-alerte (fenêtre provisoire de 7 jours).
    const proche = `Vidange e2e ${suffixe}`;
    await saisir(proche, "30", isoLocal(new Date(Date.now() - 27 * jour)));
    await expect(plans.getByRole("row", { name: new RegExp(proche) })).toContainText("Pré-alerte");
  });

  test("une demande d'OT est qualifiée, puis son historique horodaté s'affiche", async ({ page }) => {
    const label = `Bruit e2e ${Date.now()}`;
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/maintenance");
    await page.getByRole("button", { name: "Nouvel ordre de travail" }).click();
    const form = page.getByRole("form", { name: "Nouvel ordre de travail" });
    const equipement = form.getByLabel(/Équipement/);
    await expect(equipement.locator("option").nth(1)).toBeAttached();
    await equipement.selectOption({ index: 1 });
    await form.getByLabel(/Description de l'intervention/).fill(label);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");

    const card = () => page.locator(".task-card", { hasText: label });
    page.once("dialog", (d) => void d.accept("Roulement usé"));
    await card().getByRole("button", { name: "Qualifier" }).click();
    await expect(card().getByRole("button", { name: "Qualifier" })).toHaveCount(0);
    await card().getByText("Détail et historique").click();
    const historique = card().getByRole("list", { name: "Historique des statuts" });
    await expect(historique).toContainText("Demandé");
    await expect(historique).toContainText("Qualification : Roulement usé");
  });
});

test.describe("M8 Maintenance : habilitations exigées et seuils de fiabilité", () => {
  test("une exigence d'habilitation se saisit puis se supprime ; la fiabilité affiche ses seuils", async ({ page }) => {
    const motCle = `CACES e2e ${Date.now()}`;
    await loginAs(page, DEMO_USERS.admin);
    await page.goto("/maintenance");
    await expect(page.getByTestId("fiabilite-parc")).toContainText("Seuils d'alerte");

    const section = page.getByTestId("exigences-habilitation");
    await section.getByRole("button", { name: "Nouvelle exigence" }).click();
    const form = page.getByRole("form", { name: "Nouvelle exigence" });
    // Périmètre étroit (outillage × inspection) : sans effet sur les OT des autres scénarios joués en parallèle.
    await form.getByLabel(/Catégorie d'équipement/).selectOption("outillage");
    await form.getByLabel(/Type d'OT/).selectOption("inspection");
    await form.getByLabel(/Mot-clé/).fill(motCle);
    await form.getByRole("button", { name: "Enregistrer" }).click();
    await expect(form.getByRole("status")).toHaveText("Enregistré.");

    const ligne = section.getByRole("row", { name: new RegExp(motCle) });
    await expect(ligne).toContainText("Outillage");
    page.once("dialog", (d) => void d.accept());
    await ligne.getByRole("button", { name: "Supprimer" }).click();
    await expect(ligne).toHaveCount(0);
  });
});

