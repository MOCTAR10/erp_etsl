import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { cleanFilterLabel, FilterBar, filtersToQuery, type FilterDef, type FilterValues } from "./FilterBar";

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
    // période : un seul contrôle « Date du document » (jj/mm/aaaa), pas deux champs date US
    expect(screen.getByRole("button", { name: "Date du document" })).toBeInTheDocument();
    // 4e critère : rangé dans « Plus de filtres »
    expect(screen.queryByLabelText("Fournisseur / client")).toBeNull();
    await user.click(screen.getByRole("button", { name: /Plus de filtres|formulaires.filtres.plus/ }));
    await user.type(await screen.findByLabelText("Fournisseur / client"), "Total");
    expect(new URLSearchParams(q).get("status")).toBe("archived");
    expect(new URLSearchParams(q).get("type")).toBe("3");
    expect(new URLSearchParams(q).get("counterparty")).toBe("Total");
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: /Effacer|effacer/ }));
    expect(q).toBe("");
  });

  it("retire les références techniques des libellés servis par l'API", () => {
    expect(cleanFilterLabel("Statut (RF-41)")).toBe("Statut");
    expect(cleanFilterLabel("Créé le")).toBe("Créé le");
  });

  it("ignore les valeurs vides", () => {
    expect(filtersToQuery({ status: "", type: " 2 " })).toBe("type=2");
  });
});
