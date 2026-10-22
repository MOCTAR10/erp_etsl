import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import "../../i18n";
import { Modal, Sheet, SheetClose } from "./Sheet";

function Harness({ onOpenChange }: { onOpenChange?: (o: boolean) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Nouveau
      </button>
      <Sheet
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          onOpenChange?.(o);
        }}
        title="Nouvelle demande d'achat"
        description="Les champs marqués * sont obligatoires."
        footer={
          <SheetClose>
            <button type="button" className="btn">
              Annuler
            </button>
          </SheetClose>
        }
      >
        <label htmlFor="objet">Objet</label>
        <input id="objet" />
      </Sheet>
    </>
  );
}

describe("<Sheet />", () => {
  it("dialogue nommé et décrit, focus piégé dedans, Échap ferme et rend le focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Nouveau" });
    await user.click(opener);
    const dialog = await screen.findByRole("dialog", { name: "Nouvelle demande d'achat" });
    expect(dialog).toHaveAccessibleDescription("Les champs marqués * sont obligatoires.");
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    await user.tab();
    await user.tab();
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(opener).toHaveFocus();
  });

  it("bouton ✕ traduit et SheetClose ferment", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onOpenChange={onOpenChange} />);
    await user.click(screen.getByRole("button", { name: "Nouveau" }));
    await user.click(await screen.findByRole("button", { name: "Fermer" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await user.click(screen.getByRole("button", { name: "Nouveau" }));
    await user.click(await screen.findByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });
});

describe("<Modal />", () => {
  it("non contrôlée : ouverte par son déclencheur", async () => {
    const user = userEvent.setup();
    render(
      <Modal trigger={<button type="button">Confirmer</button>} title="Confirmer l'émission">
        <p>Le bon de commande sera scellé.</p>
      </Modal>,
    );
    await user.click(screen.getByRole("button", { name: "Confirmer" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirmer l'émission" });
    expect(dialog).toHaveClass("ui-modal");
    expect(dialog).not.toHaveAttribute("aria-describedby");
  });
});
