import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Popover } from "./Popover";
import { Tooltip } from "./Tooltip";

describe("<Tooltip />", () => {
  it("s'affiche au focus clavier, décrit le bouton, Échap le ferme", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip content="Exporter en CSV" delay={0}>
        <button type="button" className="icon-btn" aria-label="Exporter">
          ⇩
        </button>
      </Tooltip>,
    );
    await user.tab();
    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent("Exporter en CSV");
    expect(screen.getByRole("button", { name: "Exporter" })).toHaveAccessibleDescription("Exporter en CSV");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  });
});

describe("<Popover />", () => {
  it("ouvre un dialogue nommé, focus dedans, Échap rend le focus au déclencheur", async () => {
    const user = userEvent.setup();
    render(
      <Popover trigger={<button type="button">Filtres</button>} label="Filtres avancés">
        <label>
          Statut <input />
        </label>
      </Popover>,
    );
    const trigger = screen.getByRole("button", { name: "Filtres" });
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "Filtres avancés" });
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(trigger).toHaveFocus();
  });
});
