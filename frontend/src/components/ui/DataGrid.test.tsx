import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Eye } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../../i18n";
import { DataGrid, toOrdering } from "./DataGrid";
import type { GridColumn } from "./DataGrid";

type Bc = { id: number; code: string; montant: number | null };
const rows: Bc[] = [
  { id: 1, code: "BC-9", montant: 1200 },
  { id: 2, code: "BC-10", montant: null },
  { id: 3, code: "BC-2", montant: 50 },
];
const columns: GridColumn<Bc>[] = [
  { key: "code", header: "Code", render: (r) => r.code, sortValue: (r) => r.code },
  { key: "montant", header: "Montant", render: (r) => r.montant ?? "—", sortValue: (r) => r.montant, num: true },
  { key: "libre", header: "Note", render: () => "x" },
];
const codes = () => screen.getAllByRole("row").slice(1).map((tr) => within(tr).getAllByRole("cell")[0].textContent);

describe("<DataGrid />", () => {
  it("rendu .table, colonnes num à droite, tri client cyclique (aria-sort), collation numérique", async () => {
    const user = userEvent.setup();
    render(<DataGrid columns={columns} rows={rows} caption="Bons de commande" />);
    const table = screen.getByRole("table", { name: "Bons de commande" });
    expect(table).toHaveClass("table");
    expect(screen.getByRole("columnheader", { name: /Montant/ })).toHaveClass("num");
    expect(screen.getByRole("columnheader", { name: "Note" })).not.toHaveAttribute("aria-sort");
    expect(codes()).toEqual(["BC-9", "BC-10", "BC-2"]);

    const codeHeader = screen.getByRole("columnheader", { name: /Code/ });
    await user.click(within(codeHeader).getByRole("button"));
    expect(codeHeader).toHaveAttribute("aria-sort", "ascending");
    expect(codes()).toEqual(["BC-2", "BC-9", "BC-10"]);
    await user.click(within(codeHeader).getByRole("button"));
    expect(codeHeader).toHaveAttribute("aria-sort", "descending");
    expect(codes()).toEqual(["BC-10", "BC-9", "BC-2"]);

    // valeurs vides toujours en fin de liste, dans les deux sens
    const montant = screen.getByRole("columnheader", { name: /Montant/ });
    await user.click(within(montant).getByRole("button"));
    expect(codes()).toEqual(["BC-2", "BC-9", "BC-10"]);
    await user.click(within(montant).getByRole("button"));
    expect(codes()).toEqual(["BC-9", "BC-2", "BC-10"]);
  });

  it("tri contrôlé (serveur) : n'ordonne pas, remonte le tri ; toOrdering → DRF", async () => {
    const onSortChange = vi.fn();
    const user = userEvent.setup();
    const cols: GridColumn<Bc>[] = [{ key: "code", header: "Code", render: (r) => r.code, sortKey: "numero" }];
    render(<DataGrid columns={cols} rows={rows} sort={{ id: "code", desc: false }} onSortChange={onSortChange} />);
    expect(codes()).toEqual(["BC-9", "BC-10", "BC-2"]);
    await user.click(screen.getByRole("button", { name: /Code/ }));
    expect(onSortChange).toHaveBeenCalledWith({ id: "code", desc: true });
    expect(toOrdering({ id: "code", desc: true }, cols)).toBe("-numero");
    expect(toOrdering(null, cols)).toBe("");
  });

  it("actions de ligne au clavier, ligne cliquable (Entrée)", async () => {
    const voir = vi.fn();
    const open = vi.fn();
    const user = userEvent.setup();
    render(
      <DataGrid
        columns={columns}
        rows={rows}
        onRowClick={open}
        rowActions={(r) => [{ label: `Voir ${r.code}`, icon: Eye, onSelect: () => voir(r.id) }]}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "Actions" })).toBeInTheDocument();
    const triggers = screen.getAllByRole("button", { name: "Actions de la ligne" });
    expect(triggers).toHaveLength(3);
    triggers[0].focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Voir BC-9" })).toHaveFocus());
    await user.keyboard("{Enter}");
    expect(voir).toHaveBeenCalledWith(1);
    expect(open).not.toHaveBeenCalled();

    const row = screen.getAllByRole("row")[2];
    row.focus();
    await user.keyboard("{Enter}");
    expect(open).toHaveBeenCalledWith(rows[1]);
  });

  it("clic sur un bouton, un lien ou le menu « ⋯ » d'une ligne : n'ouvre pas la ligne", async () => {
    const open = vi.fn();
    const voir = vi.fn();
    const action = vi.fn();
    const user = userEvent.setup();
    const cols: GridColumn<Bc>[] = [
      { key: "code", header: "Code", render: (r) => r.code },
      {
        key: "btn",
        header: "Action",
        render: (r) => (
          <button type="button" onClick={() => action(r.id)}>
            Valider <span>{r.code}</span>
          </button>
        ),
      },
    ];
    render(
      <DataGrid
        columns={cols}
        rows={rows}
        onRowClick={open}
        rowActions={(r) => [{ label: `Voir ${r.code}`, icon: Eye, onSelect: () => voir(r.id) }]}
      />,
    );
    // clic sur un enfant du bouton de cellule
    await user.click(screen.getAllByText("BC-9")[1]);
    expect(action).toHaveBeenCalledWith(1);
    // ouverture du menu à la souris puis choix d'une entrée (rendue dans un portail)
    await user.click(screen.getAllByRole("button", { name: "Actions de la ligne" })[0]);
    await user.click(await screen.findByRole("menuitem", { name: "Voir BC-9" }));
    expect(voir).toHaveBeenCalledWith(1);
    expect(open).not.toHaveBeenCalled();
    // clic sur une cellule texte : ouvre la ligne
    await user.click(screen.getAllByText("BC-10")[0]);
    expect(open).toHaveBeenCalledTimes(1);
    expect(open).toHaveBeenCalledWith(rows[1]);
  });

  it("zone défilante toujours atteignable au clavier et nommée (le débordement horizontal dépend de l'écran)", () => {
    const { rerender } = render(<DataGrid columns={columns} rows={rows} caption="Bons de commande" />);
    const zone = screen.getByRole("group", { name: "Bons de commande" });
    expect(zone).toHaveAttribute("tabindex", "0");
    rerender(<DataGrid columns={columns} rows={rows} />);
    expect(screen.getByRole("group", { name: "Tableau défilant" })).toHaveAttribute("tabindex", "0");
    rerender(<DataGrid columns={columns} rows={rows} maxHeight="none" />);
    expect(screen.getByRole("group", { name: "Tableau défilant" })).toHaveAttribute("tabindex", "0");
  });

  it("états : chargement (squelette + statut) puis vide (EmptyState) ; densité compacte", () => {
    const { rerender, container } = render(<DataGrid columns={columns} rows={[]} loading density="compact" />);
    expect(screen.getByRole("status")).toHaveTextContent("Chargement des lignes…");
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
    expect(screen.getByRole("table")).toHaveClass("ui-grid--compact");
    rerender(<DataGrid columns={columns} rows={[]} emptyLabel="Aucun bon de commande" />);
    expect(screen.getByText("Aucun bon de commande")).toBeInTheDocument();
  });

  it("pagination optionnelle (composant Pagination) et libellés EN", async () => {
    await i18n.changeLanguage("en");
    render(
      <DataGrid
        columns={columns}
        rows={rows}
        rowActions={() => [{ label: "View" }]}
        pagination={{ page: 1, pageSize: 20, count: 45, onPageChange: () => {} }}
      />,
    );
    expect(screen.getByRole("navigation", { name: "Pagination" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Row actions" })).toHaveLength(3);
    await i18n.changeLanguage("fr");
  });
});
