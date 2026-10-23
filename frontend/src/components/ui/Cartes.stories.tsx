import type { Story, StoryDefault } from "@ladle/react";
import { Download, Plus } from "lucide-react";

import { formatMoney } from "../../lib/format";
import { Card, SectionCard } from "./Card";
import { ChartCard } from "./ChartCard";
import { PageHeader } from "./PageHeader";
import { Pressable } from "./Pressable";
import { SectionTitle } from "./SectionTitle";

export default { title: "Kit UI / Mise en page" } satisfies StoryDefault;

const Entete = () => (
  <PageHeader
    eyebrow="Achats"
    title="Bons de commande"
    subtitle="Commandes fournisseurs émises, réceptions et facturation."
    actions={
      <>
        <button type="button" className="btn ghost">
          <Download size={16} aria-hidden /> Exporter
        </button>
        <button type="button" className="btn primary">
          <Plus size={16} aria-hidden /> Nouvelle commande
        </button>
      </>
    }
  />
);

export const EnTeteDePage: Story = () => <Entete />;
EnTeteDePage.storyName = "En tête de page";

export const EnTeteSimple: Story = () => <PageHeader title="Tableau de bord" />;
EnTeteSimple.storyName = "En tête de page titre seul";

const Sections = () => (
  <div style={{ display: "grid", gap: 16, maxWidth: 720 }}>
    <Card>Carte simple : contenu libre, bordure 1 px, ombre très douce.</Card>
    <SectionCard
      title="Engagements du mois"
      subtitle="Commandes validées non encore facturées"
      actions={<button type="button" className="btn ghost sm">Voir tout</button>}
    >
      <p style={{ margin: 0, fontVariantNumeric: "tabular-nums" }}>{formatMoney(18450000)}</p>
    </SectionCard>
    <SectionTitle>Titre de section</SectionTitle>
    <ChartCard title="Répartition par module" subtitle="12 derniers mois" height={160}>
      <div style={{ height: "100%", display: "grid", placeItems: "center", background: "var(--surface-2)", borderRadius: 8 }} className="muted">
        Zone de graphique (Recharts)
      </div>
    </ChartCard>
  </div>
);

export const CartesEtSections: Story = () => <Sections />;
CartesEtSections.storyName = "Cartes et sections";

export const Sombre: Story = () => (
  <>
    <Entete />
    <Sections />
  </>
);
Sombre.meta = { theme: "dark" };

export const Boutons: Story = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
    <button type="button" className="btn primary">Principal</button>
    <button type="button" className="btn">Secondaire</button>
    <button type="button" className="btn ghost">Discret</button>
    <button type="button" className="btn danger">Supprimer</button>
    <button type="button" className="btn primary" disabled>Désactivé</button>
    <button type="button" className="btn primary sm">Compact</button>
    <Pressable type="button" className="btn">Pressable (retour de pression)</Pressable>
  </div>
);
