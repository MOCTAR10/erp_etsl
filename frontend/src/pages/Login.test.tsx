import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "../i18n";

vi.mock("../api/client", () => ({
  login: vi.fn(),
}));

import { login } from "../api/client";
import { LoginPage } from "./Login";

const mockedLogin = vi.mocked(login);

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>dashboard-root</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedLogin.mockReset();
  localStorage.clear();
});

describe("LoginPage", () => {
  it("affiche le formulaire (email + mot de passe)", () => {
    renderLogin();
    expect(screen.getByLabelText("Adresse e-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Mot de passe")).toBeInTheDocument();
  });

  it("redirige vers / après un login réussi", async () => {
    mockedLogin.mockResolvedValue({
      tokens: { access: "a", refresh: "r" },
      user: { email: "admin@etls.local", first_name: "Admin", role: "admin" } as never,
    });
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Adresse e-mail"), "admin@etls.local");
    await user.type(screen.getByLabelText("Mot de passe"), "Etls#Demo2026");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(screen.getByText("dashboard-root")).toBeInTheDocument());
    expect(mockedLogin).toHaveBeenCalledWith("admin@etls.local", "Etls#Demo2026");
  });

  it("affiche une erreur si les identifiants sont invalides", async () => {
    mockedLogin.mockRejectedValue(new Error("401"));
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Adresse e-mail"), "bad@etls.local");
    await user.type(screen.getByLabelText("Mot de passe"), "wrong");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(screen.getByText("Identifiants incorrects.")).toBeInTheDocument());
  });

  it("désactive le bouton pendant la soumission", async () => {
    let resolve!: (v: never) => void;
    mockedLogin.mockReturnValue(new Promise((r) => (resolve = r)));
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Adresse e-mail"), "admin@etls.local");
    await user.type(screen.getByLabelText("Mot de passe"), "Etls#Demo2026");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(screen.getByRole("button", { name: "Chargement…" })).toBeDisabled();
    resolve(undefined as never);
  });
});
