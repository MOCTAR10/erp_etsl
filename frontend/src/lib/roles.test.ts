import { describe, expect, it } from "vitest";

import i18n from "../i18n";
import { initiales, roleLabel } from "./roles";

const t = (k: string, o?: Record<string, unknown>) => i18n.t(k, o) as string;

describe("roleLabel", () => {
  it("affiche un libellé lisible, jamais le code brut", async () => {
    await i18n.changeLanguage("fr");
    expect(roleLabel(t, "pdg")).toBe("Président-directeur général");
    expect(roleLabel(t, "chef_atelier")).toBe("Chef d'atelier");
  });

  it("code inconnu : libellé reconstruit plutôt qu'une clé i18n", () => {
    expect(roleLabel(t, "chef_projet")).toBe("Chef projet");
    expect(roleLabel(t, undefined)).toBe("");
  });
});

describe("initiales", () => {
  it("prend les deux premières initiales", () => {
    expect(initiales("Admin ETSL")).toBe("AE");
    expect(initiales("rh@etls.local")).toBe("RE");
  });
});
