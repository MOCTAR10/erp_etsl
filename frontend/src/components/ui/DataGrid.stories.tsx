import type { Story, StoryDefault } from "@ladle/react";
import { useState } from "react";

import { formatDateShort, formatMoney } from "../../lib/format";
import { Badge } from "./Badge";
import { DataGrid } from "./DataGrid";
import type { GridColumn } from "./DataGrid";
import { DataTable, actionsColumn } from "./DataTable";
import { FilterBar } from "./FilterBar";
import type { FilterDef, FilterValues } from "./FilterBar";
import { Pagination } from "./Pagination";
import { SearchField } from "./SearchField";

export default { title: "Kit UI / Tableaux et filtres" } satisfies StoryDefault;

type Facture = { id: number; code: string; fournisseur: string; date: string; montant: number; statut: string };

const FACTURES: Facture[] = [
  { id: 1, code: "FF-2026-0311", fournisseur: "SOGAFRIC Services", date: "2026-10-02", montant: 4250000, statut: "Comptabilisée" },
  { id: 2, code: "FF-2026-0312", fournisseur: "Global Rental Gabon", date: "2026-10-05", montant: 18900000, statut: "À rapprocher" },
  { id: 3, code: "FF-2026-0313", fournisseur: "Port-Gentil Hydraulique", date: "2026-10-09", montant: 760000, statut: "Brouillon" },
  { id: 4, code: "FF-2026-0314", fournisseur: "Services pétroliers de l'Ogooué", date: "2026-10-12", montant: 1234567890, statut: "Comptabilisée" },
];

const TON: Record<string, "ok" | "warn" | "neutral"> = { Comptabilisée: "ok", "À rapprocher": "warn", Brouillon: "neutral" };

const COLONNES: GridColumn<Facture>[] = [
  { key: "code", header: "Référence", render: (r) => <strong>{r.code}</strong>, sortValue: (r) => r.code },
  { key: "fournisseur", header: "Fournisseur", render: (r) => r.fournisseur, sortValue: (r) => r.fournisseur },
  { key: "date", header: "Date", kind: "date", render: (r) => formatDateShort(r.date), sortValue: (r) => r.date },
  { key: "montant", header: "Montant", num: true, render: (r) => formatMoney(r.montant), sortValue: (r) => r.montant },
  { key: "statut", header: "Statut", render: (r) => <Badge tone={TON[r.statut]}>{r.statut}</Badge> },
];

const Grille = () => (
  <DataGrid
    caption="Factures fournisseurs"
    columns={COLONNES}
    rows={FACTURES}
    initialSort={{ id: "date", desc: true }}
    rowActions={(r) => [
      { label: "Ouvrir", onSelect: () => undefined },
      "separator",
      { label: `Annuler ${r.code}`, danger: true, onSelect: () => undefined },
    ]}
  />
);

export const GrilleTriable: Story = () => <Grille />;
GrilleTriable.storyName = "Grille triable avec menu de ligne";

export const Compacte: Story = () => <DataGrid caption="Factures fournisseurs" columns={COLONNES} rows={FACTURES} density="compact" />;

export const Chargement: Story = () => <DataGrid caption="Factures fournisseurs" columns={COLONNES} rows={[]} loading skeletonRows={4} />;

export const Vide: Story = () => (
  <DataGrid
    caption="Factures fournisseurs"
    columns={COLONNES}
    rows={[]}
    emptyLabel="Aucune facture"
    emptyHint="Les factures saisies ou importées apparaîtront ici."
  />
);

export const AvecActionsDeLigne: Story = () => (
  <DataTable
    caption="Factures fournisseurs"
    columns={[
      ...COLONNES,
      actionsColumn<Facture>("Actions", (r) => [
        { label: "Comptabiliser", path: `/api/achats/factures/${r.id}/comptabiliser/`, tone: "primary" },
        { label: "Rejeter", path: `/api/achats/factures/${r.id}/rejeter/`, tone: "danger" },
      ]),
    ]}
    rows={FACTURES}
  />
);
AvecActionsDeLigne.storyName = "DataTable et colonne des actions";

export const PaginationServeur: Story = () => {
  const [page, setPage] = useState(2);
  const [taille, setTaille] = useState(20);
  return <Pagination page={page} pageSize={taille} count={137} onPageChange={setPage} onPageSizeChange={setTaille} />;
};
PaginationServeur.storyName = "Pagination";

const DEFS: FilterDef[] = [
  {
    champ: "statut",
    type: "choix",
    libelle: "Statut",
    choix: [
      { valeur: "brouillon", libelle: "Brouillon" },
      { valeur: "comptabilisee", libelle: "Comptabilisée" },
    ],
  },
  { champ: "date", type: "date", libelle: "Date de facture", parametres: ["date__gte", "date__lte"] },
  { champ: "montant", type: "nombre", libelle: "Montant", parametres: ["montant__gte", "montant__lte"] },
  { champ: "global_rental", type: "bool", libelle: "Global Rental" },
];

const Filtres = () => {
  const [valeurs, setValeurs] = useState<FilterValues>({ statut: "brouillon" });
  const [texte, setTexte] = useState("");
  return (
    <FilterBar
      defs={DEFS}
      value={valeurs}
      onChange={setValeurs}
      search={<SearchField value={texte} onChange={setTexte} placeholder="Rechercher une facture…" />}
    />
  );
};

export const BarreDeFiltres: Story = () => <Filtres />;
BarreDeFiltres.storyName = "Barre de filtres et recherche";

export const Sombre: Story = () => (
  <div style={{ display: "grid", gap: 16 }}>
    <Filtres />
    <Grille />
  </div>
);
Sombre.meta = { theme: "dark" };
