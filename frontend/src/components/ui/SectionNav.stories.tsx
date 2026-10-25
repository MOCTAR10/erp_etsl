import type { Story, StoryDefault } from "@ladle/react";

import { formatMoney } from "../../lib/format";
import { SectionCard } from "./Card";
import { FileField } from "./FileField";
import { Kpi } from "./Kpi";
import { PageHeader } from "./PageHeader";
import { SectionNav } from "./SectionNav";

export default { title: "Kit UI / Navigation de sections" } satisfies StoryDefault;

const SECTIONS = [
  { id: "sn-synthese", label: "Synthèse" },
  { id: "sn-factures", label: "Factures fournisseurs", count: 4 },
  { id: "sn-lettrage", label: "Lettrage" },
  { id: "sn-banque", label: "Rapprochement bancaire" },
  { id: "sn-clotures", label: "Clôtures mensuelles" },
  { id: "sn-declarations", label: "Déclarations fiscales" },
];

const Lignes = ({ n }: { n: number }) => (
  <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
    {Array.from({ length: n }, (_, i) => (
      <li key={i} className="muted">
        Écriture OD-2026-{String(140 + i).padStart(4, "0")} — {formatMoney(1250000 + i * 337000)}
      </li>
    ))}
  </ul>
);

/** Écran long type Comptabilité : la barre reste collée en haut, l'ancre de la section lue est surlignée. */
const Ecran = () => (
  <div style={{ padding: "0 24px 40px", ["--page-pad-x" as string]: "24px" }}>
    <PageHeader title="Comptabilité" subtitle="Écritures, lettrage, rapprochement et clôtures de l'exercice 2026." />
    <SectionNav items={SECTIONS} />
    <div style={{ display: "grid", gap: 24, marginTop: 24 }}>
      <section id="sn-synthese" className="kpis" style={{ marginBottom: 0 }}>
        <Kpi label="Résultat de l'exercice" value={3337000000} kind="money" hint="Au 30 septembre 2026" />
        <Kpi label="Factures à comptabiliser" value={4} hint="Dont 1 en retard" />
        <Kpi label="Comptes à lettrer" value={27} hint="411 et 401" />
      </section>
      <SectionCard title="Factures fournisseurs" subtitle="À comptabiliser ce mois-ci">
        <div id="sn-factures">
          <Lignes n={8} />
        </div>
      </SectionCard>
      {SECTIONS.slice(2).map((s, i) => (
        <section key={s.id} id={s.id} className="card" style={{ padding: 20 }}>
          <h3 style={{ marginTop: 0 }}>{s.label}</h3>
          <Lignes n={6 + i * 2} />
        </section>
      ))}
    </div>
  </div>
);

export const Ecranlong: Story = () => <Ecran />;
Ecranlong.storyName = "Ecran long avec sections";

export const Sombre: Story = () => <Ecran />;
Sombre.meta = { theme: "dark" };

export const Selecteurdefichier: Story = () => (
  <div style={{ display: "grid", gap: 16, maxWidth: 520, padding: 24 }}>
    <div className="field">
      <label htmlFor="sn-mt940">Relevé bancaire MT940</label>
      <FileField id="sn-mt940" accept=".sta,.mt940,.txt" />
    </div>
    <FileField aria-label="Photo du constat" accept="image/*" capture="environment" buttonLabel="Choisir une photo" />
    <FileField aria-label="Import SAGE" disabled />
  </div>
);
Selecteurdefichier.storyName = "Selecteur de fichier";
