import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pencil, Trash2 } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../../i18n";
import { Menu } from "./Menu";

describe("<Menu />", () => {
  it("bouton « ⋯ » libellé, ouverture au clavier, Entrée lance l'action, focus rendu", async () => {
    const edit = vi.fn();
    const user = userEvent.setup();
    render(
      <Menu
        items={[
          { label: "Modifier", icon: Pencil, onSelect: edit, shortcut: "E" },
          "separator",
          { label: "Supprimer", icon: Trash2, danger: true },
          false,
        ]}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Plus d'actions" });
    trigger.focus();
    await user.keyboard("{Enter}");
    const menu = await screen.findByRole("menu");
    expect(screen.getAllByRole("menuitem")).toHaveLength(2);
    expect(menu.querySelector(".ui-menu-sep")).not.toBeNull();
    expect(screen.getByRole("menuitem", { name: /Supprimer/ })).toHaveClass("danger");
    await waitFor(() => expect(screen.getByRole("menuitem", { name: /Modifier/ })).toHaveFocus());
    await user.keyboard("{Enter}");
    expect(edit).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(trigger).toHaveFocus();
  });

  it("Échap ferme ; le clic sur le déclencheur ne remonte pas au parent", async () => {
    const parent = vi.fn();
    const user = userEvent.setup();
    render(
      <div onClick={parent}>
        <Menu label="Actions BC-12" items={[{ label: "Voir" }]} />
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "Actions BC-12" }));
    expect(await screen.findByRole("menu")).toBeInTheDocument();
    expect(parent).not.toHaveBeenCalled();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("libellé par défaut traduit (EN)", async () => {
    await i18n.changeLanguage("en");
    render(<Menu items={[{ label: "View" }]} />);
    expect(screen.getByRole("button", { name: "More actions" })).toBeInTheDocument();
    await i18n.changeLanguage("fr");
  });
});
