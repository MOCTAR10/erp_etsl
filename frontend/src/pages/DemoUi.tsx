// TEMPORAIRE — page de vérification visuelle des primitives (annulée par git revert).
import { Copy, Download, Eye, FileText, Home, Pencil, Receipt, Settings, Trash2, Users } from "lucide-react";
import { useState } from "react";

import {
  Badge,
  CommandPalette,
  DataGrid,
  DatePicker,
  DateRangePicker,
  Menu,
  Modal,
  Sheet,
  SheetClose,
  Tooltip,
  notify,
} from "../components/ui";
import type { DateRangeValue, GridColumn } from "../components/ui";

type Bc = { id: number; code: string; fournisseur: string; date: string; montant: number | null; statut: string };
const ROWS: Bc[] = [
  { id: 1, code: "BC-2026-0042", fournisseur: "Perenco Services Gabon", date: "2026-10-14", montant: 25_400_000, statut: "Émis" },
  { id: 2, code: "BC-2026-0041", fournisseur: "Global Rental SA", date: "2026-10-12", montant: 8_750_000, statut: "Brouillon" },
  { id: 3, code: "BC-2026-0039", fournisseur: "Schlumberger Port-Gentil", date: "2026-10-09", montant: null, statut: "Validé" },
  { id: 4, code: "BC-2026-0037", fournisseur: "Total Énergies Marketing", date: "2026-10-03", montant: 1_250_000, statut: "Réceptionné" },
  { id: 5, code: "BC-2026-0031", fournisseur: "Bolloré Logistics", date: "2026-09-28", montant: 312_500_000, statut: "Émis" },
];
const fcfa = (n: number | null) => (n === null ? "—" : `${new Intl.NumberFormat("fr-FR").format(n)} FCFA`);
const fr = (iso: string) => iso.split("-").reverse().join("/");

const COLUMNS: GridColumn<Bc>[] = [
  { key: "code", header: "Référence", render: (r) => <strong>{r.code}</strong>, sortValue: (r) => r.code },
  { key: "fournisseur", header: "Fournisseur", render: (r) => r.fournisseur, sortValue: (r) => r.fournisseur },
  { key: "date", header: "Date", render: (r) => fr(r.date), sortValue: (r) => r.date },
  {
    key: "statut",
    header: "Statut",
    render: (r) => <Badge tone={r.statut === "Brouillon" ? "neutral" : r.statut === "Émis" ? "brand" : "ok"}>{r.statut}</Badge>,
  },
  { key: "montant", header: "Montant", render: (r) => fcfa(r.montant), sortValue: (r) => r.montant, num: true },
];

export function DemoUiPage() {
  const [sheet, setSheet] = useState(false);
  const [modal, setModal] = useState(false);
  const [cmd, setCmd] = useState(false);
  const [date, setDate] = useState("2026-10-22");
  const [range, setRange] = useState<DateRangeValue>({ from: "2026-10-01", to: "2026-10-15" });
  const [dense, setDense] = useState(false);
  return (
    <div>
      <header className="page-header">
        <h2>Primitives</h2>
      </header>
      <div className="card" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16 }}>
        <div className="field" style={{ width: 200, marginBottom: 0 }}>
          <label htmlFor="demo-date">Date du document</label>
          <DatePicker id="demo-date" name="document_date" value={date} onChange={setDate} />
        </div>
        <div className="field" style={{ width: 260, marginBottom: 0 }}>
          <label htmlFor="demo-range">Période</label>
          <DateRangePicker id="demo-range" value={range} onChange={setRange} />
        </div>
        <button type="button" className="btn primary" data-demo="sheet" onClick={() => setSheet(true)}>
          Nouvelle demande
        </button>
        <button type="button" className="btn" data-demo="modal" onClick={() => setModal(true)}>
          Confirmer
        </button>
        <button type="button" className="btn ghost" data-demo="cmd" onClick={() => setCmd(true)}>
          Palette
        </button>
        <button
          type="button"
          className="btn ghost"
          data-demo="toast"
          onClick={() => {
            notify.success("Bon de commande émis", { description: "BC-2026-0042 · Perenco Services Gabon" });
            notify.error("Échec de l'enregistrement", { description: "Le serveur a refusé la pièce (409)." });
            notify.info("Synchronisation terminée");
          }}
        >
          Notifications
        </button>
        <Tooltip content="Exporter la liste en CSV">
          <button type="button" className="icon-btn" aria-label="Exporter" data-demo="tooltip">
            <Download size={16} aria-hidden />
          </button>
        </Tooltip>
        <Menu
          label="Actions de la page"
          items={[
            { type: "label", label: "Liste" },
            { label: "Exporter en CSV", icon: Download, shortcut: "Ctrl+E" },
            { label: "Dupliquer", icon: Copy },
            "separator",
            { label: "Supprimer la sélection", icon: Trash2, danger: true },
          ]}
        />
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
          <input type="checkbox" checked={dense} onChange={(e) => setDense(e.target.checked)} /> Compact
        </label>
      </div>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <DataGrid
          columns={COLUMNS}
          rows={ROWS}
          caption="Bons de commande"
          density={dense ? "compact" : "comfortable"}
          initialSort={{ id: "date", desc: true }}
          rowActions={(r) => [
            { label: "Ouvrir", icon: Eye },
            { label: "Modifier", icon: Pencil, shortcut: "E", disabled: r.statut !== "Brouillon" },
            "separator",
            { label: "Annuler la pièce", icon: Trash2, danger: true },
          ]}
          pagination={{ page: 1, pageSize: 20, count: 45, onPageChange: () => {} }}
        />
      </div>
      <div className="card" style={{ padding: 0, overflow: "hidden", marginTop: 16 }}>
        <DataGrid columns={COLUMNS} rows={[]} caption="Vide" emptyLabel="Aucun bon de commande" emptyHint="Créez une demande d'achat pour commencer." />
      </div>
      <div className="card" style={{ padding: 0, overflow: "hidden", marginTop: 16 }}>
        <DataGrid columns={COLUMNS} rows={[]} caption="Chargement" loading skeletonRows={3} />
      </div>
      <Sheet
        open={sheet}
        onOpenChange={setSheet}
        title="Nouvelle demande d'achat"
        description="Les champs marqués * sont obligatoires. La demande part en validation à l'enregistrement."
        footer={
          <>
            <SheetClose>
              <button type="button" className="btn ghost">
                Annuler
              </button>
            </SheetClose>
            <button type="submit" form="demo-form" className="btn primary">
              Enregistrer
            </button>
          </>
        }
      >
        <form id="demo-form" onSubmit={(e) => e.preventDefault()}>
          <div className="field">
            <label htmlFor="d-objet">Objet *</label>
            <input id="d-objet" defaultValue="Location de grue 50 t — chantier Rabi" />
          </div>
          <div className="field">
            <label htmlFor="d-date">Date de besoin</label>
            <DatePicker id="d-date" defaultValue="2026-11-03" />
          </div>
          <div className="field">
            <label htmlFor="d-montant">Montant estimé</label>
            <input id="d-montant" defaultValue="8 750 000" />
          </div>
        </form>
      </Sheet>
      <Modal
        open={modal}
        onOpenChange={setModal}
        title="Émettre le bon de commande ?"
        description="BC-2026-0041 sera scellé : il ne pourra plus être modifié, seulement annulé par avenant."
        footer={
          <>
            <SheetClose>
              <button type="button" className="btn ghost">
                Annuler
              </button>
            </SheetClose>
            <button type="button" className="btn primary">
              Émettre
            </button>
          </>
        }
      />
      <CommandPalette
        open={cmd}
        onOpenChange={setCmd}
        hotkey={false}
        groups={[
          {
            heading: "Pages",
            items: [
              { id: "p1", label: "Tableau de bord", icon: Home, shortcut: "G D" },
              { id: "p2", label: "Achats", icon: Receipt, hint: "M2" },
              { id: "p3", label: "Juridique & GED", icon: FileText, hint: "M11" },
              { id: "p4", label: "RH & paie", icon: Users, hint: "M9" },
            ],
          },
          { heading: "Actions", items: [{ id: "a1", label: "Paramètres ETSL", icon: Settings }] },
        ]}
      />
    </div>
  );
}
