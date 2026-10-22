import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "../../i18n";
import { AppToaster, notify } from "./Toaster";

describe("<AppToaster /> + notify", () => {
  it("affiche succès / erreur avec description, région nommée, thème suivant data-theme", async () => {
    document.documentElement.setAttribute("data-theme", "dark");
    render(<AppToaster />);
    act(() => {
      notify.success("Bon de commande émis", { description: "BC-2026-0042" });
      notify.error("Échec de l'enregistrement");
    });
    expect(await screen.findByText("Bon de commande émis")).toBeInTheDocument();
    expect(screen.getByText("BC-2026-0042")).toBeInTheDocument();
    expect(await screen.findByText("Échec de l'enregistrement")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /Notifications/ })).toBeInTheDocument();
    expect(document.querySelector("[data-sonner-toaster]")).toHaveAttribute("data-sonner-theme", "dark");
    expect(document.querySelector(".ui-toast--success")).not.toBeNull();
    act(() => {
      notify.dismiss();
    });
    document.documentElement.removeAttribute("data-theme");
  });
});
