import { describe, expect, it } from "vitest";

import { cleanLabel } from "./libelle";

describe("cleanLabel", () => {
  it("retire les références d'exigences et de modules", () => {
    expect(cleanLabel("Circuit administratif-financier (RF-ERP-W1)")).toBe("Circuit administratif-financier");
    expect(cleanLabel("Rapports d'exécution (M3)")).toBe("Rapports d'exécution");
    expect(cleanLabel("Tableau de bord Direction (C1)")).toBe("Tableau de bord Direction");
  });

  it("garde les parenthèses ordinaires et gère l'absence de libellé", () => {
    expect(cleanLabel("Pièces d'achat (BC, réceptions)")).toBe("Pièces d'achat (BC, réceptions)");
    expect(cleanLabel("Contrats (10 ans)")).toBe("Contrats (10 ans)");
    expect(cleanLabel(null)).toBe("");
  });
});
