import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import { ActionBar } from "./ActionBar";

vi.mock("../../api/client", () => ({ api: { post: vi.fn() } }));

const traiter = {
  label: "Décider du traitement",
  path: "/api/qualite/non-conformites/1/traiter/",
  prompt: { name: "traitement", label: "Traitement…", options: [{ value: "reprise", label: "Reprise" }, { value: "rejet", label: "Rejet" }] },
};

function setup() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ActionBar actions={[traiter]} />
    </QueryClientProvider>,
  );
}

describe("<ActionBar /> — choix avant action", () => {
  it("n'appelle l'API qu'après choix confirmé, avec la valeur dans le corps", async () => {
    vi.mocked(api.post).mockResolvedValue({});
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: "Décider du traitement" }));
    const confirmer = screen.getByRole("button", { name: /Confirmer|Confirm|actionBar.confirmer/ });
    expect(confirmer).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByLabelText("Traitement…"), "rejet");
    await user.click(confirmer);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(traiter.path, { traitement: "rejet" }));
  });

  it("annuler revient aux boutons sans appel", async () => {
    vi.mocked(api.post).mockClear();
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: "Décider du traitement" }));
    await user.click(screen.getByRole("button", { name: /Annuler|Cancel|actionBar.annuler/ }));
    expect(screen.getByRole("button", { name: "Décider du traitement" })).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
});
