import { describe, expect, it } from "vitest";

import { displayName } from "./people";

describe("displayName", () => {
  it("n'affiche jamais une adresse e-mail comme nom", () => {
    expect(displayName("demo.logistique@etls.local")).toBe("Logistique");
    expect(displayName("jean-paul.mba@etsl.ga")).toBe("Jean-Paul Mba");
    expect(displayName({ first_name: "", last_name: "", email: "demo.rh@etls.local" })).toBe("RH");
  });

  it("garde un nom complet tel quel", () => {
    expect(displayName("Logistique Magasin")).toBe("Logistique Magasin");
    expect(displayName({ first_name: "Awa", last_name: "Ndong" })).toBe("Awa Ndong");
    expect(displayName({ full_name: "Paul Obame" })).toBe("Paul Obame");
  });

  it("renvoie le repli si absent", () => {
    expect(displayName(null)).toBe("—");
    expect(displayName("  ")).toBe("—");
    expect(displayName(undefined, "Inconnu")).toBe("Inconnu");
  });
});
