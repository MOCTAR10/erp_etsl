import { describe, expect, it } from "vitest";

import { corpsEdition, libelleCourt, optionPourValeur, optionsCodees, parModule, SaisieInvalide, type ParametreEtsl } from "./parametres";

describe("paramètres codés (A-12)", () => {
  const methode =
    "Calcul du % d'avancement : 1 = heures pointées / prévues, 2 = quantités réalisées / commandées, 3 = dernier % déclaré (rapport d'avancement)";
  it("lit les options décrites dans le libellé", () => {
    expect(optionsCodees("Méthode (1 = coûts engagés / budget M11, 2 = situations de travaux M3)")).toEqual({
      "1": "coûts engagés / budget M11",
      "2": "situations de travaux M3",
    });
    expect(optionsCodees(methode)["3"]).toBe("dernier % déclaré (rapport d'avancement)");
  });
  it("affiche l'option retenue plutôt que le chiffre", () => {
    expect(optionPourValeur(methode, "1.00")).toBe("Heures pointées / prévues");
    expect(optionPourValeur("Déduction du coût GLOBAL RENTAL (618) : 1 = dès la marge brute, 3 = en marge nette", "3.00")).toBe("En marge nette");
    expect(optionPourValeur("Sans options", "1")).toBeNull();
  });
  it("raccourcit le libellé sans perdre le sens", () => {
    expect(libelleCourt(methode)).toBe("Calcul du % d'avancement");
    expect(libelleCourt("Clé de répartition des charges de structure (1 = heures productives, 2 = chiffre d'affaires)")).toBe(
      "Clé de répartition des charges de structure",
    );
    expect(libelleCourt("Déduction du coût GLOBAL RENTAL (618) : 1 = dès la marge brute")).toBe("Déduction du coût GLOBAL RENTAL (618)");
    expect(libelleCourt("Délai de clôture")).toBe("Délai de clôture");
  });
});

const base: ParametreEtsl = {
  id: "1",
  module: "hse",
  module_label: "M7 HSE",
  modele: "hse.ParametreHse",
  code: "DELAI",
  label: "Délai",
  groupe: "",
  valeur: "30",
  unite: "jours",
  type_valeur: "decimal",
  provisoire: true,
  confirme_le: null,
  confirme_par: null,
  edition: { method: "PATCH", path: "/api/hse/parametres/1/", champ: "valeur", extra: {} },
  confirmation: "/api/hse/parametres/1/confirmer/",
  ecran: "/hse",
};

describe("corpsEdition", () => {
  it("normalise un nombre saisi avec une virgule", () => {
    expect(corpsEdition(base, " 12,5 ")).toEqual({ valeur: "12.5" });
  });

  it("refuse un nombre invalide et un entier décimal", () => {
    expect(() => corpsEdition(base, "abc")).toThrow(SaisieInvalide);
    expect(() => corpsEdition({ ...base, type_valeur: "entier" }, "2.5")).toThrow(SaisieInvalide);
  });

  it("analyse le JSON (paramètres juridiques) et ajoute les champs fixes (révision datée de la paie)", () => {
    const juridique = { ...base, type_valeur: "json" as const, edition: { ...base.edition, method: "POST" as const } };
    expect(corpsEdition(juridique, '{"a": [90, 60]}')).toEqual({ valeur: { a: [90, 60] } });
    expect(() => corpsEdition(juridique, "{a:")).toThrow(SaisieInvalide);
    const paie = { ...base, edition: { ...base.edition, extra: { date_effet: "2026-10-22" } } };
    expect(corpsEdition(paie, "150000")).toEqual({ date_effet: "2026-10-22", valeur: "150000" });
  });

  it("utilise le champ propre à l'application (rétention GED, texte transverse)", () => {
    const ged = { ...base, type_valeur: "entier" as const, edition: { ...base.edition, champ: "retention_years" } };
    expect(corpsEdition(ged, "10")).toEqual({ retention_years: "10" });
    const texte = { ...base, type_valeur: "texte" as const, edition: { ...base.edition, champ: "texte" } };
    expect(corpsEdition(texte, "Dimanche 02:00")).toEqual({ texte: "Dimanche 02:00" });
    expect(() => corpsEdition(texte, "  ")).toThrow(SaisieInvalide);
  });
});

describe("corpsEdition — gabarit composite", () => {
  it("répartit l'objet JSON dans le corps et refuse un non-objet", () => {
    const gabarit = { ...base, type_valeur: "json" as const, edition: { ...base.edition, champ: "*" } };
    expect(corpsEdition(gabarit, '{"separateur": ";", "colonnes": {"compte": "A"}}')).toEqual({
      separateur: ";",
      colonnes: { compte: "A" },
    });
    expect(() => corpsEdition(gabarit, "[1]")).toThrow(SaisieInvalide);
  });
});

describe("parModule", () => {
  it("regroupe par module en conservant l'ordre", () => {
    const rows = [base, { ...base, id: "2", module: "users", module_label: "Socle" }, { ...base, id: "3" }];
    expect(parModule(rows).map((g) => [g.module, g.rows.length])).toEqual([
      ["hse", 2],
      ["users", 1],
    ]);
  });
});
