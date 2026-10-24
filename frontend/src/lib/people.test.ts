import { describe, expect, it } from "vitest";

import { displayName, personInitials, personTitle } from "./people";

const t = (key: string, opts?: Record<string, unknown>) =>
  key === "shell.roles.secretaire_general"
    ? "Secrétaire général"
    : key === "premiumPilotage.people.unknown"
      ? "Utilisateur"
      : String(opts?.defaultValue ?? key);

describe("displayName", () => {
  it("préfère le nom complet", () => {
    expect(displayName(t, { first_name: "Awa", last_name: "Ndong", email: "awa@etls.local" })).toBe("Awa Ndong");
    expect(displayName(t, { full_name: "Jean Mba", role: "pdg" })).toBe("Jean Mba");
  });

  it("se replie sur le libellé du rôle, jamais sur l'e-mail", () => {
    expect(displayName(t, { email: "secretariat@etls.local", role: "secretaire_general" })).toBe("Secrétaire général");
    expect(displayName(t, { name: "dga@etls.local", role: "chef_projet" })).toBe("Chef projet");
    expect(displayName(t, { email: "x@etls.local" })).toBe("Utilisateur");
    expect(displayName(t, null)).toBe("Utilisateur");
  });

  it("initiales et infobulle", () => {
    expect(personInitials(t, { first_name: "Awa", last_name: "Ndong" })).toBe("AN");
    expect(personTitle(t, { role: "secretaire_general", email: "s@etls.local" })).toBe("Secrétaire général — s@etls.local");
  });
});
