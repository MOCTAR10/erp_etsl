import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import i18n from "../i18n";

vi.mock("../api/client", () => ({ api: { post: vi.fn() } }));

import { api } from "../api/client";
import type { Budget, BudgetRevision } from "../types";
import { BudgetCard, revisionColumns } from "./ControleGestion";

const budget = {
  id: "b1", code: "BUD-00001", label: "Atelier", type_budget: "charge", statut: "brouillon",
  montant: "5000000", has_amount_access: true, analytic_code: null, axis_code: null, nb_revisions: 0,
  visa_daf_par: null, visa_cg_par: null,
} as unknown as Budget;

function renderCard(b: Budget) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BudgetCard b={b} index={0} />
    </QueryClientProvider>,
  );
}

describe("M11 — double visa DAF + CG depuis l'écran", () => {
  it("envoie le visa choisi dans le corps de la requête (sinon l'API répond 400)", async () => {
    vi.mocked(api.post).mockResolvedValue({});
    const user = userEvent.setup();
    renderCard(budget);
    expect(screen.getByText("Visa DAF en attente")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approuver" }));
    await user.selectOptions(screen.getByLabelText("Visa à apposer…"), "daf");
    await user.click(screen.getByRole("button", { name: /Confirmer/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/controle-gestion/budgets/b1/approuver/", { visa: "daf" }));
  });

  it("ne propose plus que le visa manquant une fois le visa DAF posé", async () => {
    const user = userEvent.setup();
    renderCard({ ...budget, visa_daf_par: "u1" });
    expect(screen.getByText("Visa DAF posé")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approuver" }));
    const select = screen.getByLabelText("Visa à apposer…");
    expect(select).toHaveTextContent("Visa Contrôle de gestion");
    expect(select).not.toHaveTextContent("Visa DAF");
  });

  it("l'application d'une révision envoie aussi le visa", async () => {
    vi.mocked(api.post).mockResolvedValue({});
    const user = userEvent.setup();
    const rev = { id: "r1", statut: "brouillon", visa_daf_par: null, visa_cg_par: "u2" } as unknown as BudgetRevision;
    const col = revisionColumns((k, o) => i18n.t(k, o) as string).find((c) => c.key === "statut")!;
    render(<QueryClientProvider client={new QueryClient()}>{col.render(rev)}</QueryClientProvider>);
    expect(screen.getByText("Visa CG posé")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Appliquer" }));
    await user.selectOptions(screen.getByLabelText("Visa à apposer…"), "daf");
    await user.click(screen.getByRole("button", { name: /Confirmer/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/controle-gestion/revisions/r1/appliquer/", { visa: "daf" }));
  });
});
