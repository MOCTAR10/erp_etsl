import type { Story, StoryDefault } from "@ladle/react";

import { formatMoney } from "../../lib/format";
import { Badge } from "./Badge";
import { Board, BoardCard, BoardColumn, CardActions } from "./Board";

export default { title: "Kit UI / Kanban" } satisfies StoryDefault;

const COMMANDES = [
  { id: 1, code: "BC-2026-0141", fournisseur: "SOGAFRIC Services", montant: 4250000 },
  { id: 2, code: "BC-2026-0142", fournisseur: "Global Rental Gabon", montant: 18900000 },
  { id: 3, code: "BC-2026-0143", fournisseur: "Port-Gentil Hydraulique", montant: 760000 },
];

const Carte = ({ c, actions = false }: { c: (typeof COMMANDES)[number]; actions?: boolean }) => (
  <BoardCard className="task-card">
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
      <strong>{c.code}</strong>
      <Badge tone="warn">À valider</Badge>
    </div>
    <div className="muted">{c.fournisseur}</div>
    <div style={{ fontVariantNumeric: "tabular-nums" }}>{formatMoney(c.montant)}</div>
    {actions ? (
      <CardActions
        actions={[
          { label: "Valider", path: "/api/achats/commandes/1/valider/", tone: "primary" },
          { label: "Renvoyer en brouillon", path: "/api/achats/commandes/1/brouillon/" },
          { label: "Annuler", path: "/api/achats/commandes/1/annuler/", tone: "danger", confirm: "Annuler la commande ?" },
        ]}
      />
    ) : null}
  </BoardCard>
);

const Kanban = () => (
  <Board label="Bons de commande par statut">
    <BoardColumn title="Brouillon" tone="neutral" count={0} />
    <BoardColumn title="À valider" tone="warn" count={3} summary={formatMoney(23910000)} limit={2}>
      {COMMANDES.map((c) => (
        <Carte key={c.id} c={c} actions />
      ))}
    </BoardColumn>
    <BoardColumn title="Émis" tone="brand" count={1}>
      <Carte c={COMMANDES[0]} />
    </BoardColumn>
    <BoardColumn title="Réceptionné" tone="ok" count={0} emptyLabel="Aucune réception" />
  </Board>
);

export const Colonnes: Story = () => <Kanban />;
Colonnes.storyName = "Colonnes cartes actions et colonne vide";

export const Sombre: Story = () => <Kanban />;
Sombre.meta = { theme: "dark" };
