import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import { QuickForm } from "./QuickForm";

vi.mock("../../api/client", () => ({ api: { post: vi.fn() } }));

const fields = [
  { name: "description", label: "Description", required: true },
  { name: "priorite", label: "Priorité", type: "select" as const, options: [{ value: "haute", label: "Haute" }] },
  { name: "note", label: "Note" },
];

function setup() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <QuickForm title="Nouvel OT" endpoint="/api/maintenance/ordres/" fields={fields} />
    </QueryClientProvider>,
  );
}

describe("<QuickForm />", () => {

  it("s'ouvre, envoie les champs remplis (vides retirés) et confirme", async () => {
    vi.mocked(api.post).mockResolvedValue({});
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /Nouvel OT/ }));
    await user.type(screen.getByLabelText(/Description/), "Fuite");
    await user.selectOptions(screen.getByLabelText("Priorité"), "haute");
    await user.click(screen.getByRole("button", { name: /Enregistrer|Save|quickForm.save/ }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/maintenance/ordres/", { description: "Fuite", priorite: "haute" }),
    );
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("affiche l'erreur de validation renvoyée par le serveur", async () => {
    vi.mocked(api.post).mockImplementation(() =>
      Promise.reject(Object.assign(new Error("400"), { detail: { description: ["Ce champ est obligatoire."] } })),
    );
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /Nouvel OT/ }));
    await user.type(screen.getByLabelText(/Description/), "x");
    await user.click(screen.getByRole("button", { name: /Enregistrer|Save|quickForm.save/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ce champ est obligatoire.");
  });
});
