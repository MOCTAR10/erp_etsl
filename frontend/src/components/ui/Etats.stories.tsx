import type { Story, StoryDefault } from "@ladle/react";
import { Inbox, Plus } from "lucide-react";

import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { BoardSkeleton, KpiSkeleton, Skeleton } from "./Skeleton";

export default { title: "Kit UI / États" } satisfies StoryDefault;

export const Vide: Story = () => (
  <div className="card">
    <EmptyState
      icon={Inbox}
      label="Aucune demande d'achat"
      hint="Les demandes créées par les chefs de service apparaîtront ici."
      action={
        <button type="button" className="btn primary sm">
          <Plus size={14} aria-hidden /> Nouvelle demande
        </button>
      }
    />
  </div>
);

export const VideCompact: Story = () => (
  <div className="card" style={{ maxWidth: 280 }}>
    <EmptyState compact label="Aucun élément" />
  </div>
);
VideCompact.storyName = "Vide compact";

export const Erreur: Story = () => (
  <div className="card">
    <ErrorState message="Impossible de charger les commandes." onRetry={() => undefined} />
  </div>
);

export const Chargement: Story = () => (
  <div style={{ display: "grid", gap: 16 }}>
    <div className="card" style={{ display: "grid", gap: 8 }}>
      <Skeleton style={{ height: 16, width: "40%" }} />
      <Skeleton style={{ height: 12, width: "80%" }} />
      <Skeleton style={{ height: 12, width: "65%" }} />
    </div>
    <div style={{ maxWidth: 260 }}>
      <KpiSkeleton />
    </div>
    <BoardSkeleton cols={3} rows={2} />
  </div>
);

export const Sombre: Story = () => (
  <div style={{ display: "grid", gap: 16 }}>
    <div className="card">
      <EmptyState icon={Inbox} label="Aucune demande d'achat" hint="Rien à traiter pour le moment." />
    </div>
    <div className="card">
      <ErrorState message="Impossible de charger les commandes." onRetry={() => undefined} />
    </div>
    <BoardSkeleton cols={3} rows={1} />
  </div>
);
Sombre.meta = { theme: "dark" };
