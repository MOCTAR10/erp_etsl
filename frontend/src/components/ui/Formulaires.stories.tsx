import type { Story, StoryDefault } from "@ladle/react";
import { useState } from "react";

import { ActionBar } from "./ActionBar";
import { DatePicker, DateRangePicker } from "./DatePicker";
import type { DateRangeValue } from "./DatePicker";
import { QuickForm } from "./QuickForm";

export default { title: "Kit UI / Formulaires" } satisfies StoryDefault;

const Champs = () => {
  const [date, setDate] = useState("2026-10-23");
  const [periode, setPeriode] = useState<DateRangeValue>({ from: "2026-10-01", to: "2026-10-31" });
  return (
    <div className="card" style={{ display: "grid", gap: 16, maxWidth: 480 }}>
      <div className="field">
        <label htmlFor="ladle-texte">Objet</label>
        <input id="ladle-texte" defaultValue="Location grue 50 t" />
      </div>
      <div className="field">
        <label htmlFor="ladle-choix">Site</label>
        <select id="ladle-choix" defaultValue="pog">
          <option value="pog">Port-Gentil</option>
          <option value="lbv">Libreville</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="ladle-date">Date de livraison</label>
        <DatePicker id="ladle-date" value={date} onChange={setDate} />
      </div>
      <div className="field">
        <label htmlFor="ladle-periode">Période</label>
        <DateRangePicker id="ladle-periode" value={periode} onChange={setPeriode} />
      </div>
      <div className="field">
        <label htmlFor="ladle-off">Champ désactivé</label>
        <DatePicker id="ladle-off" value="" disabled />
      </div>
    </div>
  );
};

export const ChampsEtDates: Story = () => <Champs />;
ChampsEtDates.storyName = "Champs dates période et désactivé";

export const FormulaireRapide: Story = () => (
  <QuickForm
    title="Nouvelle demande d'achat"
    endpoint="/api/achats/demandes/"
    submitLabel="Créer la demande"
    fields={[
      { name: "objet", label: "Objet", required: true },
      { name: "date_besoin", label: "Date de besoin", type: "date" },
      { name: "montant_estime", label: "Montant estimé (FCFA)", type: "number", min: 0 },
      {
        name: "priorite",
        label: "Priorité",
        type: "select",
        options: [
          { value: "normale", label: "Normale" },
          { value: "urgente", label: "Urgente" },
        ],
      },
      { name: "motif", label: "Motif", type: "textarea" },
    ]}
  />
);
FormulaireRapide.storyName = "Formulaire rapide en panneau";

export const BarreDActions: Story = () => (
  <ActionBar
    actions={[
      { label: "Valider", path: "/api/hse/permis/1/valider/", tone: "primary" },
      { label: "Demander un complément", path: "/api/hse/permis/1/complement/", prompt: { name: "motif", label: "Motif" } },
      { label: "Rejeter", path: "/api/hse/permis/1/rejeter/", tone: "danger", confirm: "Rejeter ce permis ?" },
    ]}
  />
);
BarreDActions.storyName = "Barre des actions de workflow";

export const Sombre: Story = () => <Champs />;
Sombre.meta = { theme: "dark" };
