import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Home, Moon, Receipt } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../../i18n";
import { CommandPalette, normalizeSearch } from "./CommandPalette";
import type { CommandGroupDef } from "./CommandPalette";

const groups = (go = vi.fn()): CommandGroupDef[] => [
  {
    heading: "Pages",
    items: [
      { id: "compta", label: "Comptabilité", icon: Home, keywords: ["/comptabilite"], onSelect: () => go("compta") },
      { id: "ged", label: "Juridique & GED", icon: Home, shortcut: "G J", onSelect: () => go("ged") },
    ],
  },
  { heading: "Actions", items: [{ id: "theme", label: "Mode sombre", icon: Moon, onSelect: () => go("theme") }] },
];

const options = () => screen.getAllByRole("option").map((o) => o.textContent);

describe("normalizeSearch", () => {
  it("ignore casse et accents", () => {
    expect(normalizeSearch("Comptabilité")).toBe("comptabilite");
  });
});

describe("<CommandPalette /> (cmdk)", () => {
  it("Ctrl+K ouvre, recherche floue sans accents, Entrée lance et ferme", async () => {
    const go = vi.fn();
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<CommandPalette groups={groups(go)} onSelect={onSelect} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Palette de commandes" })).toBeInTheDocument();
    const input = screen.getByRole("combobox");
    await waitFor(() => expect(input).toHaveFocus());
    expect(screen.getByText("Pages")).toBeInTheDocument();
    await user.type(input, "cpta");
    expect(options()[0]).toContain("Comptabilité");
    await user.keyboard("{Enter}");
    expect(go).toHaveBeenCalledWith("compta");
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "compta" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("flèches + mots-clés, état vide traduit, Échap ferme (mode contrôlé)", async () => {
    const go = vi.fn();
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(<CommandPalette open onOpenChange={onOpenChange} groups={groups(go)} />);
    const input = await screen.findByRole("combobox");
    await waitFor(() => expect(input).toHaveFocus());
    await user.keyboard("{ArrowDown}{Enter}");
    expect(go).toHaveBeenCalledWith("ged");
    await user.clear(input);
    await user.type(input, "/comptabilite");
    expect(options()).toHaveLength(1);
    await user.clear(input);
    await user.type(input, "zzzz");
    expect(screen.getByText("Aucun résultat")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("recherche asynchrone : délai, résultats serveur ajoutés, saisie courte ignorée", async () => {
    const search = vi.fn(async (q: string) => [
      { heading: "Bons de commande", items: [{ id: `bc-${q}`, label: "BC-2026-0042", hint: "Achats", icon: Receipt }] },
    ]);
    const user = userEvent.setup();
    render(<CommandPalette open groups={groups()} search={search} debounce={10} />);
    const input = await screen.findByRole("combobox");
    await user.type(input, "b");
    expect(search).not.toHaveBeenCalled();
    await user.type(input, "c42");
    expect(await screen.findByText("BC-2026-0042")).toBeInTheDocument();
    expect(screen.getByText("Bons de commande")).toBeInTheDocument();
    expect(search).toHaveBeenLastCalledWith("bc42", expect.any(AbortSignal));
  });

  it("libellés anglais", async () => {
    await act(() => i18n.changeLanguage("en"));
    render(<CommandPalette open groups={groups()} />);
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search a page, an action…")).toBeInTheDocument();
    await act(() => i18n.changeLanguage("fr"));
  });
});
