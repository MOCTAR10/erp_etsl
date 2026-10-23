import type { Story, StoryDefault } from "@ladle/react";
import { Compass, Copy, FileText, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";

import { CommandPalette } from "./CommandPalette";
import type { CommandGroupDef } from "./CommandPalette";
import { Menu } from "./Menu";
import { Popover } from "./Popover";
import { Modal, Sheet, SheetClose } from "./Sheet";
import { AppToaster, notify } from "./Toaster";
import { Tooltip } from "./Tooltip";

export default { title: "Kit UI / Superpositions" } satisfies StoryDefault;

const MenuCommande = () => (
  <Menu
    label="Actions de la commande"
    items={[
      { type: "label", label: "Commande BC-2026-0141" },
      { label: "Modifier", icon: Pencil, onSelect: () => undefined, shortcut: "E" },
      { label: "Dupliquer", icon: Copy, onSelect: () => undefined },
      { label: "Exporter (désactivé)", icon: FileText, disabled: true },
      "separator",
      { label: "Supprimer", icon: Trash2, danger: true, onSelect: () => undefined },
    ]}
  />
);

export const MenuDActions: Story = () => <MenuCommande />;
MenuDActions.storyName = "Menu des actions";

export const InfoBulleEtPopover: Story = () => (
  <div style={{ display: "flex", gap: 16, alignItems: "center", paddingTop: 48 }}>
    <Tooltip content="Compte 618 : Global Rental">
      <button type="button" className="btn ghost">
        Survoler
      </button>
    </Tooltip>
    <Popover
      label="Détail du solde"
      trigger={
        <button type="button" className="btn">
          Ouvrir le détail
        </button>
      }
    >
      <div style={{ padding: 4, display: "grid", gap: 4 }}>
        <strong>Solde disponible</strong>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>12 450 000 FCFA</span>
      </div>
    </Popover>
  </div>
);
InfoBulleEtPopover.storyName = "Info bulle et popover";

const Panneaux = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
    <Sheet
      title="Nouvelle réception"
      description="Saisie des quantités reçues"
      trigger={
        <button type="button" className="btn">
          Panneau latéral
        </button>
      }
      footer={
        <>
          <SheetClose>
            <button type="button" className="btn ghost">
              Annuler
            </button>
          </SheetClose>
          <button type="button" className="btn primary">
            Enregistrer
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="ladle-qte">Quantité reçue</label>
        <input id="ladle-qte" type="number" defaultValue={12} />
      </div>
    </Sheet>
    <Modal
      title="Comptabiliser la facture ?"
      description="L'écriture devient immuable ; seule une extourne pourra l'annuler."
      trigger={
        <button type="button" className="btn primary">
          Fenêtre de confirmation
        </button>
      }
      footer={
        <>
          <SheetClose>
            <button type="button" className="btn ghost">
              Annuler
            </button>
          </SheetClose>
          <button type="button" className="btn primary">
            Comptabiliser
          </button>
        </>
      }
    />
  </div>
);

export const PanneauEtFenetre: Story = () => <Panneaux />;
PanneauEtFenetre.storyName = "Panneau latéral et fenêtre modale";

export const Notifications: Story = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
    <AppToaster />
    <button type="button" className="btn" onClick={() => notify.success("Commande validée.")}>
      Succès
    </button>
    <button
      type="button"
      className="btn"
      onClick={() => notify.error("Refus du serveur", { description: "Budget de l'affaire dépassé." })}
    >
      Erreur
    </button>
    <button type="button" className="btn" onClick={() => notify.info("Synchronisation terminée.")}>
      Information
    </button>
    <button type="button" className="btn" onClick={() => notify.warning("Échéance dans 15 jours.")}>
      Avertissement
    </button>
  </div>
);

const GROUPES: CommandGroupDef[] = [
  {
    heading: "Navigation",
    items: [
      { id: "achats", label: "Achats", hint: "Demandes, commandes, factures", icon: Compass },
      { id: "direction", label: "Direction / BI", hint: "Indicateurs de pilotage", icon: Compass },
      { id: "paie", label: "Paie (accès restreint)", disabled: true },
    ],
  },
];

export const PaletteDeCommandes: Story = () => {
  const [ouvert, setOuvert] = useState(true);
  return (
    <>
      <button type="button" className="btn" onClick={() => setOuvert(true)}>
        Ouvrir la palette
      </button>
      <CommandPalette open={ouvert} onOpenChange={setOuvert} groups={GROUPES} hotkey={false} />
    </>
  );
};
PaletteDeCommandes.storyName = "Palette de commandes";

export const Sombre: Story = () => (
  <div style={{ display: "grid", gap: 16, justifyItems: "start" }}>
    <MenuCommande />
    <Panneaux />
  </div>
);
Sombre.meta = { theme: "dark" };
