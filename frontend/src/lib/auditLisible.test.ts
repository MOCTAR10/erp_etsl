import { describe, expect, it } from "vitest";

import { champsVisibles, regrouperAudit, valeurLisible } from "./auditLisible";

describe("piste d'audit lisible", () => {
  it("rend null, ISO et UUID lisibles", () => {
    expect(valeurLisible(null)).toBe("—");
    expect(valeurLisible("")).toBe("—");
    expect(valeurLisible(true)).toBe("Oui");
    expect(valeurLisible("2026-10-24T15:29:50.328636+00:00")).not.toContain("T15");
    expect(valeurLisible("efc7254e-46ea-4a1b-9c3d-0123456789ab")).toBe("#efc7254e");
    expect(valeurLisible("x".repeat(80))).toHaveLength(61);
  });

  it("écarte les champs techniques", () => {
    expect(champsVisibles(["analyse_le", "analyse_par_id", "updated_at", "statut"])).toEqual(["analyse_le", "statut"]);
  });

  it("regroupe les lignes consécutives identiques seulement", () => {
    const l = (id: string, minute: string, type = "controle_gestion.budget") => ({
      id,
      user_email: "a@etls.local",
      action: "update",
      object_type: type,
      created_at: `2026-10-24T15:${minute}:10Z`,
      detail: { champs: ["analyse_le"] },
    });
    const g = regrouperAudit([l("1", "29"), l("2", "29"), l("3", "29", "hse.incident"), l("4", "29")]);
    expect(g.map((r) => [r.id, r.repetitions])).toEqual([
      ["1", 2],
      ["3", 1],
      ["4", 1],
    ]);
  });
});
