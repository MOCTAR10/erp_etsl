import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "../../i18n";

vi.mock("../../api/client", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

import { api } from "../../api/client";
import type { Budget } from "../../types";
import { SaisieBudgetaireSection } from "./SaisieBudgetaireSection";

const b = (statut: string, id: string) => ({ id, code: `BUD-${id}`, label: `Budget ${id}`, statut }) as unknown as Budget;

function renderSection(budgets: Budget[]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SaisieBudgetaireSection fiscalYear="1" budgets={budgets} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(api.get).mockReset();
  vi.mocked(api.post).mockReset();
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.includes("consommations-stock")) return { depots: [], consommations_par_axe: [] };
    return { results: [] };
  });
});

describe("M11 — saisie budgétaire", () => {
  it("n'offre la ligne mensuelle que pour un budget brouillon et la révision que pour un budget approuvé", () => {
    renderSection([b("brouillon", "1")]);
    expect(screen.getByRole("button", { name: /Ligne mensuelle/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Nouvelle révision/ })).not.toBeInTheDocument();
  });

  it("propose la révision une fois le budget approuvé, et plus la ligne mensuelle", () => {
    renderSection([b("approuve", "2")]);
    expect(screen.getByRole("button", { name: /Nouvelle révision/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ligne mensuelle/ })).not.toBeInTheDocument();
  });

  it("crée un budget sur l'exercice courant", async () => {
    vi.mocked(api.post).mockResolvedValue({});
    const user = userEvent.setup();
    renderSection([]);
    await user.click(screen.getByRole("button", { name: /Nouveau budget/ }));
    await user.type(screen.getByLabelText(/Intitulé/), "Atelier 2026");
    await user.type(screen.getByLabelText(/Montant annuel/), "5000");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        "/api/controle-gestion/budgets/",
        expect.objectContaining({ label: "Atelier 2026", montant: "5000", type_budget: "charge", fiscal_year: "1" }),
      ),
    );
  });

  it("affiche le résultat de la détection des écarts", async () => {
    vi.mocked(api.post).mockResolvedValue({ analyses: ["ECA-00001"] });
    const user = userEvent.setup();
    renderSection([]);
    await user.click(screen.getByRole("button", { name: /Détecter les écarts/ }));
    expect(await screen.findByText(/1 analyse\(s\) ouverte\(s\) : ECA-00001/)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/api/controle-gestion/analyses-ecart/detecter/");
  });

  it("indique l'absence de valorisation de stock figée", async () => {
    renderSection([]);
    expect(await screen.findByText(/Aucune valorisation mensuelle figée/)).toBeInTheDocument();
  });
});
