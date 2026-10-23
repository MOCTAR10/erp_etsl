import { describe, expect, it } from "vitest";

import { DEFAULT_LANDING, landingForRole } from "./landing";

describe("landingForRole", () => {
  it("laisse l'administrateur et le chef de service sur le tableau de bord", () => {
    // `admin` sur `/` : contrat de `auth.spec.ts` (« atterrit sur le tableau de bord »).
    expect(landingForRole("admin")).toBe("/");
    expect(landingForRole("chef_service")).toBe("/");
  });

  it("envoie la Direction générale sur Direction / BI", () => {
    expect(landingForRole("pdg")).toBe("/direction");
    expect(landingForRole("dga")).toBe("/direction");
    expect(landingForRole("direction")).toBe("/direction");
  });

  it("envoie chaque métier sur son module", () => {
    expect(landingForRole("rh")).toBe("/rh-paie");
    expect(landingForRole("finance")).toBe("/comptabilite");
    expect(landingForRole("comptable")).toBe("/comptabilite");
    expect(landingForRole("qaqc")).toBe("/qualite");
    expect(landingForRole("hse")).toBe("/hse");
    expect(landingForRole("logistique")).toBe("/logistique");
    expect(landingForRole("maintenance")).toBe("/maintenance");
    expect(landingForRole("chef_atelier")).toBe("/operations");
    expect(landingForRole("directeur_operations")).toBe("/operations");
    expect(landingForRole("directeur_projets")).toBe("/kanban");
    expect(landingForRole("secretaire_general")).toBe("/circuits");
  });

  it("retombe sur le tableau de bord si le rôle est inconnu ou absent", () => {
    expect(landingForRole("role_inexistant")).toBe(DEFAULT_LANDING);
    expect(landingForRole(null)).toBe(DEFAULT_LANDING);
    expect(landingForRole(undefined)).toBe(DEFAULT_LANDING);
    expect(landingForRole("")).toBe(DEFAULT_LANDING);
  });
});
