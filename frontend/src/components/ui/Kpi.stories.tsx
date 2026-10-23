import type { Story, StoryDefault } from "@ladle/react";
import { Banknote, ClipboardCheck, ShieldAlert, Truck } from "lucide-react";

import { AnimatedNumber } from "./AnimatedNumber";
import { Kpi } from "./Kpi";
import { ProgressBar } from "./Progress";
import { KpiGridSkeleton } from "./Skeleton";
import { Sparkline } from "./Sparkline";

export default { title: "Kit UI / Indicateurs" } satisfies StoryDefault;

const Grille = () => (
  <div className="kpi-grid">
    <Kpi label="Chiffre d'affaires" value={25000000} kind="money" icon={Banknote} hint="Exercice en cours" />
    <Kpi label="Commandes ouvertes" value={42} icon={Truck} tone="neutral" />
    <Kpi label="Taux de conformité" value={96.4} kind="percent" icon={ClipboardCheck} tone="ok" />
    <Kpi label="Incidents HSE" value={3} icon={ShieldAlert} tone="err" hint="Dont 1 avec arrêt" />
  </div>
);

export const Kpis: Story = () => <Grille />;
Kpis.storyName = "KPI grille";

export const MontantLong: Story = () => (
  <div className="kpi-grid" style={{ maxWidth: 420 }}>
    <Kpi label="Engagements de l'exercice" value={1234567890} kind="money" icon={Banknote} />
    <Kpi label="Montant masqué (droits)" value={null} kind="money" icon={Banknote} hint="Montants réservés" />
  </div>
);
MontantLong.storyName = "KPI montant long et masqué";

export const Chargement: Story = () => <KpiGridSkeleton count={4} />;
Chargement.storyName = "KPI chargement";

export const KpiSombre: Story = () => <Grille />;
KpiSombre.storyName = "KPI sombre";
KpiSombre.meta = { theme: "dark" };

export const Nombres: Story = () => (
  <div className="card" style={{ display: "grid", gap: 16, maxWidth: 420 }}>
    <div style={{ fontSize: 28, fontVariantNumeric: "tabular-nums" }}>
      <AnimatedNumber value={1250000} />
    </div>
    <Sparkline values={[12, 18, 15, 22, 19, 27, 31, 29]} label="Évolution sur 8 semaines" />
    <Sparkline values={[5]} label="Un seul point" />
  </div>
);
Nombres.storyName = "Nombre animé et sparkline";

export const Progression: Story = () => (
  <div className="card" style={{ display: "grid", gap: 16, maxWidth: 420 }}>
    <ProgressBar value={0} label="Non démarré" />
    <ProgressBar value={45} label="Avancement chantier" />
    <ProgressBar value={80} label="Budget consommé" tone="warn" />
    <ProgressBar value={112} label="Dépassement" tone="err" />
    <ProgressBar value={100} label="Terminé" tone="ok" />
  </div>
);
Progression.storyName = "Barre de progression";
