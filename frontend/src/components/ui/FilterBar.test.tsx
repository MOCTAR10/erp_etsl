import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { FilterBar, filtersToQuery, type FilterDef, type FilterValues } from "./FilterBar";

const defs: FilterDef[] = [
  { champ: "status", type: "choix", libelle: "Statut", choix: [{ valeur: "draft", libelle: "Brouillon" }, { valeur: "archived", libelle: "Archivé" }] },
  { champ: "type", type: "fk", libelle: "Type de document" },
  { champ: "dossier", type: "fk", libelle: "Dossier" },
  { champ: "document_date", type: "date", libelle: "Date du document" },
  { champ: "counterparty", type: "texte", libelle: "Fournisseur / client" },
];

function Harness({ onQuery }: { onQuery: (q: string) => void }) {
  const [v, setV] = useState<FilterValues>({});
  return (
    <FilterBar
      defs={defs}
      value={v}
      options={{ type: [{ valeur: "3", libelle: "Contrat" }] }}
      onChange={(next) => {
        setV(next);
        onQuery(filtersToQuery(next));
      }}
    />
  );
}

describe("<FilterBar />", () => {
  it("combine les critères en paramètres d'URL et les efface", async () => {
    const user = userEvent.setup();
    let q = "";
    render(<Harness onQuery={(x) => (q = x)} />);
    // clé étrangère sans valeurs fournies (dossier) : masquée
    expect(screen.queryByLabelText("Dossier")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Statut"), "archived");
    await user.selectOptions(screen.getByLabelText("Type de document"), "3");
    await user.type(screen.getByLabelText(/Date du document — /, { selector: "[id$=-du]" }), "2026-01-01");
    await user.type(screen.getByLabelText("Fournisseur / client"), "Total");
    expect(new URLSearchParams(q).get("status")).toBe("archived");
    expect(new URLSearchParams(q).get("type")).toBe("3");
    expect(new URLSearchParams(q).get("document_date__gte")).toBe("2026-01-01");
    expect(new URLSearchParams(q).get("counterparty")).toBe("Total");
    await user.click(screen.getByRole("button"));
    expect(q).toBe("");
  });

  it("ignore les valeurs vides", () => {
    expect(filtersToQuery({ status: "", type: " 2 " })).toBe("type=2");
  });
});
