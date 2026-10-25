import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import "../../i18n";
import { ModuleSettings } from "./ModuleSettings";

afterEach(() => {
  try {
    window.localStorage.clear();
  } catch {
    // stockage indisponible : rien à purger
  }
});

describe("ModuleSettings (B11)", () => {
  it("est replié par défaut et ne monte pas son contenu", () => {
    render(
      <ModuleSettings id="t-parametres">
        <p>Barème CNSS</p>
      </ModuleSettings>,
    );
    expect(screen.getByRole("heading", { name: "Paramètres du module" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Afficher les paramètres/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Barème CNSS")).toBeNull();
  });

  it("se déplie au clic et mémorise l'état", async () => {
    const { unmount } = render(
      <ModuleSettings id="t-parametres">
        <p>Barème CNSS</p>
      </ModuleSettings>,
    );
    await userEvent.click(screen.getByRole("button", { name: /Afficher les paramètres/ }));
    expect(screen.getByText("Barème CNSS")).toBeVisible();
    expect(screen.getByRole("button", { name: /Masquer les paramètres/ })).toHaveAttribute("aria-expanded", "true");
    unmount();
    render(
      <ModuleSettings id="t-parametres">
        <p>Barème CNSS</p>
      </ModuleSettings>,
    );
    expect(screen.getByText("Barème CNSS")).toBeVisible();
  });

  it("se déplie quand la navigation de sections pose le focus sur la section", () => {
    render(
      <ModuleSettings id="t-focus">
        <p>Gabarit SAGE</p>
      </ModuleSettings>,
    );
    const section = document.getElementById("t-focus") as HTMLElement;
    section.setAttribute("tabindex", "-1");
    act(() => section.focus());
    expect(screen.getByText("Gabarit SAGE")).toBeVisible();
  });
});
