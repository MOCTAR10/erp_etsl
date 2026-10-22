import { describe, expect, it } from "vitest";

import { corpsEdition, parModule, SaisieInvalide, type ParametreEtsl } from "./parametres";

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

describe("parModule", () => {
  it("regroupe par module en conservant l'ordre", () => {
    const rows = [base, { ...base, id: "2", module: "users", module_label: "Socle" }, { ...base, id: "3" }];
    expect(parModule(rows).map((g) => [g.module, g.rows.length])).toEqual([
      ["hse", 2],
      ["users", 1],
    ]);
  });
});
