import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "../i18n";

vi.mock("../api/client", () => ({
  login: vi.fn(),
  mfaEnrolement: vi.fn(),
  mfaVerification: vi.fn(),
}));

import { login, mfaVerification } from "../api/client";
import { useAuth } from "../store/auth";
import { LoginPage } from "./Login";

const mockedLogin = vi.mocked(login);
const mockedMfa = vi.mocked(mfaVerification);

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>dashboard-root</div>} />
        <Route path="/comptabilite" element={<div>page-comptabilite</div>} />
        <Route path="/rh-paie" element={<div>page-rh-paie</div>} />
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

  it("atterrit sur le module du rôle, pas sur le tableau de bord", async () => {
    mockedLogin.mockResolvedValue({
      tokens: { access: "a", refresh: "r" },
      user: { email: "finance@etls.local", first_name: "Finance", role: "finance" } as never,
    });
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Adresse e-mail"), "finance@etls.local");
    await user.type(screen.getByLabelText("Mot de passe"), "Etls#Demo2026");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(screen.getByText("page-comptabilite")).toBeInTheDocument());
    expect(screen.queryByText("dashboard-root")).not.toBeInTheDocument();
  });

  it("atterrit sur le module RH pour le rôle rh", async () => {
    mockedLogin.mockResolvedValue({
      tokens: { access: "a", refresh: "r" },
      user: { email: "rh@etls.local", first_name: "Ressources", role: "rh" } as never,
    });
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Adresse e-mail"), "rh@etls.local");
    await user.type(screen.getByLabelText("Mot de passe"), "Etls#Demo2026");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(screen.getByText("page-rh-paie")).toBeInTheDocument());
  });

  it("respecte une URL profonde demandée avant la connexion", async () => {
    mockedLogin.mockResolvedValue({
      tokens: { access: "a", refresh: "r" },
      user: { email: "logistique@etls.local", first_name: "Logistique", role: "logistique" } as never,
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={[{ pathname: "/login", state: { from: { pathname: "/rh-paie" } } }]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/rh-paie" element={<div>page-rh-paie</div>} />
          <Route path="/logistique" element={<div>page-logistique</div>} />
        </Routes>
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText("Adresse e-mail"), "logistique@etls.local");
    await user.type(screen.getByLabelText("Mot de passe"), "Etls#Demo2026");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(screen.getByText("page-rh-paie")).toBeInTheDocument());
  });

  it("explique une session expirée au lieu d'une erreur", () => {
    useAuth.setState({ expiree: true });
    renderLogin();
    expect(screen.getByRole("status")).toHaveTextContent("Votre session a expiré");
    useAuth.setState({ expiree: false });
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

  // `auth.spec.ts` / `e2e/helpers.ts` utilisent getByLabel("Mot de passe"), qui
  // matche en sous-chaîne : aucun autre libellé accessible ne doit contenir
  // « mot de passe », sinon la spec tombe en strict-mode violation.
  it("n'expose qu'un seul champ associé au libellé « Mot de passe »", () => {
    renderLogin();
    expect(screen.getAllByLabelText(/mot de passe/i)).toHaveLength(1);
    expect(screen.getAllByLabelText(/adresse e-mail/i)).toHaveLength(1);
  });

  it("affiche puis masque le mot de passe", async () => {
    const user = userEvent.setup();
    renderLogin();
    const field = screen.getByLabelText("Mot de passe");
    expect(field).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Afficher les caractères saisis" }));
    expect(field).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Masquer les caractères saisis" }));
    expect(field).toHaveAttribute("type", "password");
  });

  it("pré-remplit le formulaire depuis un compte de démonstration", async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole("button", { name: /Direction \/ Admin/ }));
    expect(screen.getByLabelText("Adresse e-mail")).toHaveValue("admin@etls.local");
    expect(screen.getByLabelText("Mot de passe")).toHaveValue("Etls#Demo2026");
  });

  it("exige le code à 6 chiffres pour un rôle sensible (étape MFA)", async () => {
    mockedLogin.mockResolvedValue({ mfa: { mfa_requis: true, mfa_enrolement: false, mfa_jeton: "j" } });
    mockedMfa.mockResolvedValue({
      tokens: { access: "a", refresh: "r" },
      user: { email: "admin@etls.local", first_name: "Admin", role: "admin" } as never,
    });
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Adresse e-mail"), "admin@etls.local");
    await user.type(screen.getByLabelText("Mot de passe"), "Etls#Demo2026");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    const champ = await screen.findByLabelText("Code à 6 chiffres");
    expect(screen.queryByText("dashboard-root")).not.toBeInTheDocument();
    await user.type(champ, "123456");
    await user.click(screen.getByRole("button", { name: "Valider le code" }));
    await waitFor(() => expect(screen.getByText("dashboard-root")).toBeInTheDocument());
    expect(mockedMfa).toHaveBeenCalledWith("j", "123456");
  });
});
