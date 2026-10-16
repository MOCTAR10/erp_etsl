import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Home, Moon } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { CommandPalette, filterItems, normalize, type PaletteItem } from "./CommandPalette";

const make = (run = vi.fn()): PaletteItem[] => [
  { id: "a", label: "Comptabilité", group: "Pages", Icon: Home, keywords: "/comptabilite", run },
  { id: "b", label: "Juridique & GED", group: "Pages", Icon: Home, run },
  { id: "c", label: "Sombre", group: "Actions", Icon: Moon, run },
];

describe("normalize / filterItems", () => {
  it("ignore casse et accents", () => {
    expect(normalize("Comptabilité")).toBe("comptabilite");
    expect(filterItems(make(), "COMPTABILITE").map((i) => i.id)).toEqual(["a"]);
    expect(filterItems(make(), "juri").map((i) => i.id)).toEqual(["b"]);
  });
  it("cherche aussi dans les mots-clés (chemin)", () => {
    expect(filterItems(make(), "/comptabilite").map((i) => i.id)).toEqual(["a"]);
  });
  it("requête vide = tout", () => {
    expect(filterItems(make(), "  ")).toHaveLength(3);
  });
});

describe("<CommandPalette />", () => {
  const setup = (run = vi.fn(), onClose = vi.fn()) => {
    render(
      <CommandPalette open onClose={onClose} items={make(run)} placeholder="Chercher" emptyLabel="Rien" />,
    );
    return { run, onClose, user: userEvent.setup() };
  };

  it("filtre en tapant puis lance l'entrée avec Entrée et se ferme", async () => {
    const { run, onClose, user } = setup();
    await user.type(screen.getByRole("combobox"), "jurid");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    await user.keyboard("{Enter}");
    expect(run).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalled();
  });

  it("navigue aux flèches (circulaire)", async () => {
    const { run, user } = setup();
    await user.keyboard("{ArrowUp}{Enter}"); // dernier élément (circulaire)
    expect(run).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("option", { selected: true })).toHaveTextContent("Sombre");
  });

  it("Échap ferme sans rien lancer", async () => {
    const { run, onClose, user } = setup();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
  });

  it("affiche l'état vide", async () => {
    const { user } = setup();
    await user.type(screen.getByRole("combobox"), "zzzz");
    expect(screen.getByText("Rien")).toBeInTheDocument();
  });
});
