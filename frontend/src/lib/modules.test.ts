import { describe, expect, it } from "vitest";

import { APP_NAV_KEY, ROUTE_APP, appForRoute, canSeeApp } from "./modules";

describe("canSeeApp", () => {
  it("filtre sur les modules du rôle", () => {
    expect(canSeeApp(["rh_paie", "hse"], "rh_paie")).toBe(true);
    expect(canSeeApp(["rh_paie", "hse"], "hse")).toBe(true);
    expect(canSeeApp(["rh_paie", "hse"], "comptabilite")).toBe(false);
  });

  it("fail-open sans `modules` (session persistée avant RF-59)", () => {
    // Le 403 du backend reste la garde finale : on ne masque rien par défaut.
    expect(canSeeApp(undefined, "juridique")).toBe(true);
    expect(canSeeApp([], "juridique")).toBe(false);
  });
});

describe("ROUTE_APP", () => {
  it("couvre les 12 applications ERP sans doublon", () => {
    const routes = Object.keys(ROUTE_APP);
    expect(routes).toHaveLength(12);
    expect(new Set(routes).size).toBe(12);
    expect(new Set(Object.values(ROUTE_APP)).size).toBe(12);
  });

  it("expose un libellé i18n pour chaque application", () => {
    for (const app of Object.values(ROUTE_APP)) {
      expect(APP_NAV_KEY[app]).toMatch(/^nav\./);
    }
  });

  it("retrouve l'application d'une route de module", () => {
    expect(appForRoute("/comptabilite")).toBe("comptabilite");
    expect(appForRoute("/controle-gestion")).toBe("controle_gestion");
    expect(appForRoute("/inconnu")).toBeUndefined();
  });
});
