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
