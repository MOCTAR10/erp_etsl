import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";

interface Ligne {
  id: string;
  period: number;
  period_label: string;
  montant: string | null;
}
interface BudgetM11 {
  id: string;
  code: string;
  label: string;
  statut: string;
  montant: string | null;
  classe_mix: string;
  lignes: Ligne[];
}
interface Revision {
  id: string;
  code: string;
  budget_code: string;
  statut: string;
  visa_daf_par: string | null;
  visa_cg_par: string | null;
  ancien_montant: string | null;
  nouveau_montant: string | null;
}
interface RevisionLigne {
  id: string;
  revision_code: string;
  period_label: string;
  ancien_montant: string | null;
  nouveau_montant: string | null;
}
interface Param {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  est_provisoire: boolean;
}
interface Axe {
  id: number;
  code: string;
  label: string;
  axis_type_label: string;
}
interface Valeur {
  id: number;
  axis_code: string;
  code: string;
  label: string;
}
interface Periode {
  id: number;
  start_date: string;
}
interface Pipe {
  categories: { categorie: string; nb: number; brut: string | null; ponderation: string; pondere: string | null }[];
  total: string | null;
  provisoire: boolean;
}
interface Imputation {
  cle_label: string;
  charges_structure: string | null;
  non_imputees: string | null;
  provisoire: boolean;
  rows: {
    affaire: string;
    code: string;
    titre: string;
    profil: string;
    part_pct: string;
    produits: string | null;
    marge_directe: string | null;
    structure_imputee: string | null;
    marge_apres_structure: string | null;
    taux_structure_reel: string | null;
    taux_structure_standard: string | null;
  }[];
}
interface Kpis {
  kpis: { code: string; libelle: string; unite: string; formule: string; valeur: string | null; cible: string; atteint: boolean | null }[];
  cibles_provisoires: boolean;
}
interface TableauBord {
  lignes: { cle: string; affaires: number; ca_prevu: string | null; marge_prevue: string | null; produits: string | null; charges: string | null; cout_gr: string | null; marge_reelle: string | null }[];
}
interface MargeAffaire {
  affaire: string;
  code: string;
  titre: string;
  client: string;
  profil: string;
  ca: string | null;
  marge: string | null;
  taux: string | null;
  validation: string;
  valide_par: string | null;
  commentaire: string;
}
interface CoutMo {
  rows: { affaire: string; ordres: number; heures: string; heures_non_valorisees: string; cout: string | null; cout_horaire_moyen: string | null }[];
}
interface Plan {
  id: string;
  code: string;
  budget_code: string;
  budget_label: string;
  centre: string;
  taux: string | null;
  actions: string;
  responsable_nom: string | null;
  echeance: string | null;
  statut: string;
  statut_label: string;
  suivi: string;
  en_retard: boolean;
}
interface Cloture {
  id: string;
  code: string;
  period_label: string;
  statut: string;
}
interface ReportingArchive {
  id: string;
  cloture_code: string;
  period_label: string;
  type_reporting: string;
  horizon: number;
  echeance: string;
  archive_le: string;
  a_temps: boolean;
  document_titre: string | null;
}
interface Revue {
  id: string;
  code: string;
  period_label: string;
  date_revue: string;
  participants: string;
  ordre_du_jour: string;
  decisions: string;
  statut: string;
  statut_label: string;
}
interface Fnp {
  id: string;
  code: string;
  date_arrete: string;
  montant: string | null;
  statut: string;
  statut_label: string;
  move_number: string | null;
  extourne_number: string | null;
}
interface FnpApercu {
  lignes: { bc: string; ligne: string; fournisseur: string; compte: string; quantite: string; montant: string | null }[];
  total: string | null;
  compte: string;
}

const money = (v: string | null | undefined) => (v === null || v === undefined ? "••••••" : formatMoney(Number(v)));
const pct = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${formatNumber(Number(v))} %`);
const BASE = "/api/controle-gestion";
/** Lignes calculées par le serveur (sans `id`) : identifiant stable pour la grille. */
const withId = <R,>(rows: R[] | undefined, id: (r: R) => string) => (rows ?? []).map((r) => ({ ...r, id: id(r) }));

function useList<T>(key: unknown[], path: string, enabled = true) {
  return useQuery({ queryKey: ["m11e", ...key], queryFn: () => api.listAll<T>(path), retry: 0, enabled }).data ?? [];
}
function useGet<T>(key: unknown[], path: string, enabled = true) {
  return useQuery({ queryKey: ["m11e", ...key], queryFn: () => api.get<T>(path), retry: 0, enabled }).data;
}

function Provisoire({ show }: { show: boolean | undefined }) {
  const { t } = useTranslation();
  return show ? <Badge tone="warn">{t("ecarts_m11.provisoire")}</Badge> : null;
}

/** Table de paramétrage (structure, taux, pondérations, cibles des KPI) : valeurs ETSL modifiables et confirmables, provisoires par défaut. */
function ParamTable({ table, title }: { table: string; title: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const rows = useList<Param>(["params", table], `${BASE}/parametres/?table=${table}`);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const done = { onSuccess: () => { setEdit(null); setError(null); void qc.invalidateQueries(); }, onError: (e: unknown) => setError(describeError(e)) };
  const save = useMutation({ mutationFn: (v: { id: string; valeur: string }) => api.patch(`${BASE}/parametres/${v.id}/`, { valeur: v.valeur }), ...done });
  const confirm = useMutation({ mutationFn: (id: string) => api.post(`${BASE}/parametres/${id}/confirmer/`), ...done });
  const columns: Column<Param>[] = [
    { key: "label", header: t("tableaux.controleGestion.parametre"), render: (p) => p.label },
    {
      key: "valeur",
      header: t("tableaux.controleGestion.valeur"),
      num: true,
      render: (p) =>
        edit?.id === p.id ? (
          <input aria-label={p.label} className="control" type="number" step="0.01" value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
        ) : (
          `${formatNumber(Number(p.valeur))} ${p.unite}`
        ),
    },
    {
      key: "statut",
      header: t("tableaux.controleGestion.statut"),
      render: (p) => (p.est_provisoire ? <Badge tone="warn">{t("ecarts_m11.provisoire")}</Badge> : <Badge tone="ok">{t("ecarts_m11.confirme")}</Badge>),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (p) =>
        edit?.id === p.id ? (
          <button type="button" className="btn primary sm" onClick={() => save.mutate(edit)}>
            {t("ecarts_m11.enregistrer")}
          </button>
        ) : (
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost sm" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>
              {t("ecarts_m11.modifier")}
            </button>
            {p.est_provisoire && (
              <button type="button" className="btn ghost sm" onClick={() => confirm.mutate(p.id)}>
                {t("ecarts_m11.confirmer")}
              </button>
            )}
          </div>
        ),
    },
  ];
  return (
    <>
      <h3>{title}</h3>
      <div data-testid={`table-${table}`}>
        <DataTable columns={columns} rows={rows} caption={title} density="compact" />
      </div>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

/** Édition d'un budget brouillon (libellé, montant, classe de Mix) et de ses lignes mensuelles. */
function EditionBrouillon({ budgets }: { budgets: BudgetM11[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const brouillons = budgets.filter((b) => b.statut === "brouillon");
  const [id, setId] = useState("");
  const [form, setForm] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const budget = brouillons.find((b) => b.id === id);
  const ok = { onSuccess: () => { setMsg({ ok: true, text: t("ecarts_m11.enregistre") }); void qc.invalidateQueries(); }, onError: (e: unknown) => setMsg({ ok: false, text: describeError(e) }) };
  const saveBudget = useMutation({ mutationFn: () => api.patch(`${BASE}/budgets/${id}/`, form), ...ok });
  const saveLigne = useMutation({ mutationFn: (v: { id: string; montant: string }) => api.patch(`${BASE}/budget-lignes/${v.id}/`, { montant: v.montant }), ...ok });
  if (brouillons.length === 0) return <p className="muted">{t("ecarts_m11.edition.aucun")}</p>;
  const lignesCols: Column<Ligne>[] = [
    { key: "periode", header: t("tableaux.controleGestion.periode"), render: (l) => l.period_label, sortValue: (l) => l.period },
    { key: "montant", header: t("tableaux.controleGestion.montant"), num: true, render: (l) => money(l.montant) },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (l) => (
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => {
            const v = window.prompt(t("ecarts_m11.edition.nouveauMontant"), l.montant ?? "");
            if (v !== null) saveLigne.mutate({ id: l.id, montant: v });
          }}
        >
          {t("ecarts_m11.modifier")}
        </button>
      ),
    },
  ];
  return (
    <div data-testid="edition-brouillon">
      <div className="field" style={{ maxWidth: "24rem" }}>
        <label htmlFor="m11-brouillon">{t("ecarts_m11.edition.budget")}</label>
        <select
          id="m11-brouillon"
          value={id}
          onChange={(e) => {
            const b = brouillons.find((x) => x.id === e.target.value);
            setId(e.target.value);
            setForm(b ? { label: b.label, montant: b.montant ?? "", classe_mix: b.classe_mix } : {});
          }}
        >
          <option value="">—</option>
          {brouillons.map((b) => (
            <option key={b.id} value={b.id}>
              {b.code} — {b.label}
            </option>
          ))}
        </select>
      </div>
      {budget && (
        <>
          <div className="quick-form-grid">
            {(["label", "montant"] as const).map((f) => (
              <div className="field" key={f}>
                <label htmlFor={`m11-ed-${f}`}>{t(`ecarts_m11.edition.${f}`)}</label>
                <input id={`m11-ed-${f}`} type={f === "montant" ? "number" : "text"} value={form[f] ?? ""} onChange={(e) => setForm({ ...form, [f]: e.target.value })} />
              </div>
            ))}
            <div className="field">
              <label htmlFor="m11-ed-mix">{t("ecarts_m11.edition.mix")}</label>
              <select id="m11-ed-mix" value={form.classe_mix ?? ""} onChange={(e) => setForm({ ...form, classe_mix: e.target.value })}>
                <option value="">—</option>
                {["A", "B", "C"].map((c) => (
                  <option key={c} value={c}>
                    Mix {c}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button type="button" className="btn primary" onClick={() => saveBudget.mutate()}>
            {t("ecarts_m11.enregistrer")}
          </button>
          <DataTable columns={lignesCols} rows={budget.lignes} caption={t("ecarts_m11.edition.budget")} density="compact" />
        </>
      )}
      {msg && (
        <p className={msg.ok ? "quick-form-ok" : "action-error"} role={msg.ok ? "status" : "alert"}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

/** Écarts M11 : révision par ligne, tables de paramétrage, axes, pipe → budget, imputation de structure, KPI, tableaux de bord,
 *  marge d'affaire, coût MO, plans d'action, reporting archivé, revue de performance, provision 408. */
export function EcartsM11Section({ fiscalYear }: { fiscalYear: number | string }) {
  const { t } = useTranslation();
  const fy = `fiscal_year=${fiscalYear}`;
  const [par, setPar] = useState("profil");
  const [cloture, setCloture] = useState("");
  const [dateFnp, setDateFnp] = useState(new Date().toISOString().slice(0, 10));
  const [dlError, setDlError] = useState<string | null>(null);

  const budgets = useList<BudgetM11>(["budgets", fiscalYear], `${BASE}/budgets/?${fy}`);
  const revisions = useList<Revision>(["revisions"], `${BASE}/revisions/`);
  const revLignes = useList<RevisionLigne>(["rev-lignes"], `${BASE}/revision-lignes/`);
  const periodes = useList<Periode>(["periodes", fiscalYear], `/api/accounting/periods/?${fy}`);
  const axes = useList<Axe>(["axes"], `${BASE}/axes/`);
  const valeurs = useList<Valeur>(["valeurs"], `${BASE}/valeurs-axes/`);
  const pipe = useGet<Pipe>(["pipe", fiscalYear], `${BASE}/pipe-budget/?${fy}`);
  const imputation = useGet<Imputation>(["imputation", fiscalYear], `${BASE}/imputation-structure/?${fy}`);
  const kpis = useGet<Kpis>(["kpis", fiscalYear], `${BASE}/kpis/?${fy}`);
  const tableau = useGet<TableauBord>(["tableau", par], `${BASE}/tableau-bord/?par=${par}`);
  const marges = useGet<{ rows: MargeAffaire[] }>(["marges"], `${BASE}/marges-affaires/`);
  const coutMo = useGet<CoutMo>(["cout-mo"], `${BASE}/cout-mo-affaires/`);
  const plans = useList<Plan>(["plans"], `${BASE}/plans-sous-activite/`);
  const clotures = useList<Cloture>(["clotures", fiscalYear], `${BASE}/clotures/?${fy}`);
  const reportings = useList<ReportingArchive>(["reportings"], `${BASE}/reportings/`);
  const revues = useList<Revue>(["revues"], `${BASE}/revues-performance/`);
  const fnps = useList<Fnp>(["fnp"], `${BASE}/provisions-fnp/`);
  const apercu = useGet<FnpApercu>(["fnp-apercu", dateFnp], `${BASE}/provisions-fnp/apercu/?date=${dateFnp}`, Boolean(dateFnp));

  const optPeriode = periodes.map((p) => ({ value: String(p.id), label: p.start_date.slice(0, 7) }));
  const revOuvertes = revisions.filter((r) => r.statut === "brouillon" && !r.visa_daf_par && !r.visa_cg_par);
  const approuves = budgets.filter((b) => b.statut !== "brouillon");
  const download = (type: string) => {
    setDlError(null);
    api.download(`${BASE}/reportings/donnees/?cloture=${cloture}&type=${type}&export=pdf`, `reporting-${type}.pdf`).catch((e) => setDlError(describeError(e)));
  };
  const actionsHeader = <span className="sr-only">{t("ui.actions")}</span>;

  return (
    <>
      <SectionCard
        title={t("ecarts_m11.budget.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("ecarts_m11.budget.nouvelleRevision")}
              endpoint={`${BASE}/revisions/`}
              fields={[
                { name: "budget", label: t("ecarts_m11.budget.budget"), type: "select", required: true, options: approuves.filter((b) => b.statut === "approuve").map((b) => ({ value: b.id, label: `${b.code} — ${b.label}` })) },
                { name: "date_revision", label: t("ecarts_m11.budget.date"), type: "date", required: true, defaultValue: new Date().toISOString().slice(0, 10) },
                { name: "commentaire", label: t("ecarts_m11.budget.commentaire") },
              ]}
            />
            {revOuvertes.length > 0 && (
              <QuickForm
                title={t("ecarts_m11.budget.reviserLigne")}
                endpoint={`${BASE}/revision-lignes/`}
                fields={[
                  { name: "revision", label: t("ecarts_m11.budget.revision"), type: "select", required: true, options: revOuvertes.map((r) => ({ value: r.id, label: `${r.code} · ${r.budget_code}` })) },
                  { name: "period", label: t("ecarts_m11.budget.periode"), type: "select", required: true, options: optPeriode },
                  { name: "nouveau_montant", label: t("ecarts_m11.budget.montantRevise"), type: "number", min: 0, step: "0.01", required: true },
                ]}
              />
            )}
          </SectionActions>
        }
      >
        <EditionBrouillon budgets={budgets} />
        <h3>{t("ecarts_m11.budget.revisionLigne")}</h3>
        <div data-testid="revision-lignes">
          <DataTable
            caption={t("ecarts_m11.budget.revisionLigne")}
            rows={revLignes}
            emptyLabel={t("tableaux.controleGestion.aucuneRevision")}
            columns={[
              { key: "revision", header: t("ecarts_m11.budget.revision"), render: (l) => l.revision_code, sortValue: (l) => l.revision_code },
              { key: "periode", header: t("ecarts_m11.budget.periode"), render: (l) => l.period_label },
              { key: "avant", header: t("ecarts_m11.budget.avant"), num: true, render: (l) => money(l.ancien_montant) },
              { key: "apres", header: t("ecarts_m11.budget.apres"), num: true, render: (l) => money(l.nouveau_montant) },
            ]}
          />
        </div>
        <p className="muted">{t("ecarts_m11.budget.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.tables.title")}>
        <p className="action-error" role="note">
          {t("ecarts_m11.bandeau")}
        </p>
        <ParamTable table="RGM_PARAM_STRUCTURE" title={t("ecarts_m11.tables.param")} />
        <ParamTable table="RGM_TAUX_STRUCTURE" title={t("ecarts_m11.tables.taux")} />
        <ParamTable table="RGM_POND_PROSPECT" title={t("ecarts_m11.tables.pond")} />
        <ParamTable table="KPI_CIBLES" title={t("ecarts_m11.tables.kpi")} />
      </SectionCard>

      <SectionCard
        title={t("ecarts_m11.axes.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("ecarts_m11.axes.nouvelAxe")}
              endpoint={`${BASE}/axes/`}
              fields={[
                { name: "code", label: t("ecarts_m11.axes.code"), required: true },
                { name: "label", label: t("ecarts_m11.axes.libelle"), required: true },
                { name: "axis_type", label: t("ecarts_m11.axes.type"), type: "select", required: true, defaultValue: "centre_cout", options: ["projet", "chantier", "centre_cout", "site"].map((v) => ({ value: v, label: t(`ecarts_m11.axes.types.${v}`) })) },
              ]}
            />
            <QuickForm
              title={t("ecarts_m11.axes.nouvelleValeur")}
              endpoint={`${BASE}/valeurs-axes/`}
              fields={[
                { name: "axis", label: t("ecarts_m11.axes.axe"), type: "select", required: true, options: axes.map((a) => ({ value: String(a.id), label: `${a.code} — ${a.label}` })) },
                { name: "code", label: t("ecarts_m11.axes.code"), required: true },
                { name: "label", label: t("ecarts_m11.axes.libelle"), required: true },
              ]}
            />
            <ActionBar actions={[{ label: t("ecarts_m11.axes.initialiser"), path: `${BASE}/axes/initialiser/`, tone: "ghost" }]} />
          </SectionActions>
        }
      >
        <div data-testid="axes-analytiques">
          <DataTable
            caption={t("ecarts_m11.axes.title")}
            rows={axes}
            columns={[
              { key: "axe", header: t("ecarts_m11.axes.axe"), render: (a) => `${a.code} — ${a.label}`, sortValue: (a) => a.code },
              { key: "type", header: t("ecarts_m11.axes.type"), render: (a) => a.axis_type_label },
              {
                key: "valeurs",
                header: t("ecarts_m11.axes.valeurs"),
                render: (a) =>
                  valeurs
                    .filter((v) => v.axis_code === a.code)
                    .map((v) => v.code)
                    .join(", ") || "—",
              },
            ]}
          />
        </div>
        <p className="muted">{t("ecarts_m11.axes.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m11.pipe.title")}
        actions={
          <ActionBar actions={[{ label: t("ecarts_m11.pipe.proposer"), path: `${BASE}/pipe-budget/proposer/`, body: { fiscal_year: fiscalYear }, confirm: t("ecarts_m11.pipe.confirm") }]} />
        }
      >
        <Provisoire show={pipe?.provisoire} />
        <div data-testid="pipe-budget">
          <DataTable
            caption={t("ecarts_m11.pipe.title")}
            rows={withId(pipe?.categories, (c) => c.categorie)}
            columns={[
              { key: "categorie", header: t("ecarts_m11.pipe.categorie"), render: (c) => t(`ecarts_m11.pipe.cat.${c.categorie}`) },
              { key: "nb", header: t("ecarts_m11.pipe.nb"), num: true, render: (c) => formatNumber(c.nb), sortValue: (c) => c.nb },
              { key: "brut", header: t("ecarts_m11.pipe.brut"), num: true, render: (c) => money(c.brut), sortValue: (c) => Number(c.brut ?? 0) },
              { key: "ponderation", header: t("ecarts_m11.pipe.ponderation"), num: true, render: (c) => pct(c.ponderation) },
              { key: "pondere", header: t("ecarts_m11.pipe.pondere"), num: true, render: (c) => money(c.pondere), sortValue: (c) => Number(c.pondere ?? 0) },
            ]}
          />
        </div>
        <p>
          <strong>{t("ecarts_m11.pipe.total")}</strong> : <span className="amount">{money(pipe?.total)}</span>
        </p>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.imputation.title")}>
        <Provisoire show={imputation?.provisoire} />
        <p>
          {t("ecarts_m11.imputation.cle")} : <strong>{imputation?.cle_label ?? "—"}</strong> · {t("ecarts_m11.imputation.structure")} : {money(imputation?.charges_structure)}
        </p>
        <div data-testid="imputation-structure">
          <DataTable
            caption={t("ecarts_m11.imputation.title")}
            rows={withId(imputation?.rows, (r) => r.affaire)}
            columns={[
              { key: "affaire", header: t("ecarts_m11.col.affaire"), render: (r) => `${r.code} · ${r.titre}`, sortValue: (r) => r.code },
              { key: "profil", header: t("ecarts_m11.col.profil"), render: (r) => r.profil },
              { key: "part", header: t("ecarts_m11.imputation.part"), num: true, render: (r) => pct(r.part_pct) },
              { key: "produits", header: t("ecarts_m11.col.produits"), num: true, render: (r) => money(r.produits), sortValue: (r) => Number(r.produits ?? 0) },
              { key: "margeDirecte", header: t("ecarts_m11.imputation.margeDirecte"), num: true, render: (r) => money(r.marge_directe) },
              { key: "imputee", header: t("ecarts_m11.imputation.imputee"), num: true, render: (r) => money(r.structure_imputee) },
              { key: "margeApres", header: t("ecarts_m11.imputation.margeApres"), num: true, render: (r) => money(r.marge_apres_structure), sortValue: (r) => Number(r.marge_apres_structure ?? 0) },
              { key: "tauxReel", header: t("ecarts_m11.imputation.tauxReel"), num: true, render: (r) => pct(r.taux_structure_reel) },
              { key: "tauxStandard", header: t("ecarts_m11.imputation.tauxStandard"), num: true, render: (r) => pct(r.taux_structure_standard) },
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.kpi.title")}>
        <Provisoire show={Boolean(kpis)} />
        <div data-testid="kpis-m11">
          <DataTable
            caption={t("ecarts_m11.kpi.title")}
            rows={withId(kpis?.kpis, (k) => k.code)}
            columns={[
              { key: "libelle", header: t("ecarts_m11.kpi.libelle"), render: (k) => k.libelle, sortValue: (k) => k.libelle },
              {
                key: "valeur",
                header: t("ecarts_m11.kpi.valeur"),
                num: true,
                render: (k) => (
                  <>
                    {k.valeur === null ? "—" : `${formatNumber(Number(k.valeur))} ${k.unite}`}{" "}
                    {k.atteint !== null && <Badge tone={k.atteint ? "ok" : "err"}>{t(k.atteint ? "ecarts_m11.kpi.atteint" : "ecarts_m11.kpi.nonAtteint")}</Badge>}
                  </>
                ),
              },
              { key: "cible", header: t("ecarts_m11.kpi.cible"), num: true, render: (k) => `${formatNumber(Number(k.cible))} ${k.unite}` },
              { key: "formule", header: t("ecarts_m11.kpi.formule"), render: (k) => <span className="muted">{k.formule}</span> },
            ]}
          />
        </div>
        <p className="muted">{t("ecarts_m11.kpi.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m11.tableau.title")}
        actions={
          <div className="field" style={{ minWidth: "14rem", margin: 0 }}>
            <label htmlFor="m11-par">{t("ecarts_m11.tableau.par")}</label>
            <select id="m11-par" value={par} onChange={(e) => setPar(e.target.value)}>
              {["profil", "client", "affaire", "responsable"].map((p) => (
                <option key={p} value={p}>
                  {t(`ecarts_m11.tableau.axes.${p}`)}
                </option>
              ))}
            </select>
          </div>
        }
      >
        <div data-testid="tableau-bord-m11">
          <DataTable
            caption={t("ecarts_m11.tableau.title")}
            rows={withId(tableau?.lignes, (l) => l.cle)}
            columns={[
              { key: "cle", header: t(`ecarts_m11.tableau.axes.${par}`), render: (l) => l.cle, sortValue: (l) => l.cle },
              { key: "affaires", header: t("ecarts_m11.tableau.affaires"), num: true, render: (l) => formatNumber(l.affaires), sortValue: (l) => l.affaires },
              { key: "caPrevu", header: t("ecarts_m11.tableau.caPrevu"), num: true, render: (l) => money(l.ca_prevu), sortValue: (l) => Number(l.ca_prevu ?? 0) },
              { key: "margePrevue", header: t("ecarts_m11.tableau.margePrevue"), num: true, render: (l) => money(l.marge_prevue) },
              { key: "produits", header: t("ecarts_m11.col.produits"), num: true, render: (l) => money(l.produits) },
              { key: "charges", header: t("ecarts_m11.tableau.charges"), num: true, render: (l) => money(l.charges) },
              { key: "coutGr", header: t("ecarts_m11.tableau.coutGr"), num: true, render: (l) => money(l.cout_gr) },
              { key: "margeReelle", header: t("ecarts_m11.tableau.margeReelle"), num: true, render: (l) => money(l.marge_reelle), sortValue: (l) => Number(l.marge_reelle ?? 0) },
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.marges.title")}>
        <div data-testid="marges-affaires">
          <DataTable
            caption={t("ecarts_m11.marges.title")}
            rows={withId(marges?.rows, (m) => m.affaire)}
            columns={[
              { key: "affaire", header: t("ecarts_m11.col.affaire"), render: (m) => `${m.code} · ${m.titre}`, sortValue: (m) => m.code },
              { key: "client", header: t("ecarts_m11.col.client"), render: (m) => m.client || "—" },
              { key: "profil", header: t("ecarts_m11.col.profil"), render: (m) => m.profil },
              { key: "ca", header: t("ecarts_m11.marges.ca"), num: true, render: (m) => money(m.ca), sortValue: (m) => Number(m.ca ?? 0) },
              {
                key: "marge",
                header: t("ecarts_m11.marges.marge"),
                num: true,
                render: (m) => (
                  <>
                    {money(m.marge)} <span className="muted">({pct(m.taux)})</span>
                  </>
                ),
              },
              {
                key: "validation",
                header: t("ecarts_m11.marges.validation"),
                render: (m) => (
                  <>
                    <Badge tone={m.validation === "validee" ? "ok" : m.validation === "rejetee" ? "err" : "warn"}>{t(`ecarts_m11.marges.statuts.${m.validation}`)}</Badge>
                    {m.valide_par ? <span className="muted"> {m.valide_par}</span> : null}
                  </>
                ),
              },
              actionsColumn<MargeAffaire & { id: string }>(t("ui.actions"), (m) => [
                { label: t("ecarts_m11.marges.valider"), path: `${BASE}/marges-affaires/${m.affaire}/valider/` },
                { label: t("ecarts_m11.marges.rejeter"), path: `${BASE}/marges-affaires/${m.affaire}/rejeter/`, tone: "danger" as const, prompt: { name: "commentaire", label: t("ecarts_m11.marges.motif") } },
              ]),
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.mo.title")}>
        <div data-testid="cout-mo-affaires">
          <DataTable
            caption={t("ecarts_m11.mo.title")}
            rows={withId(coutMo?.rows, (r) => r.affaire)}
            columns={[
              { key: "affaire", header: t("ecarts_m11.col.affaire"), render: (r) => r.affaire, sortValue: (r) => r.affaire },
              { key: "ordres", header: t("ecarts_m11.mo.ordres"), num: true, render: (r) => formatNumber(r.ordres) },
              { key: "heures", header: t("ecarts_m11.mo.heures"), num: true, render: (r) => `${formatNumber(Number(r.heures))} h`, sortValue: (r) => Number(r.heures) },
              { key: "nonValorisees", header: t("ecarts_m11.mo.nonValorisees"), num: true, render: (r) => `${formatNumber(Number(r.heures_non_valorisees))} h` },
              { key: "cout", header: t("ecarts_m11.mo.cout"), num: true, render: (r) => money(r.cout), sortValue: (r) => Number(r.cout ?? 0) },
              { key: "coutHoraire", header: t("ecarts_m11.mo.coutHoraire"), num: true, render: (r) => money(r.cout_horaire_moyen) },
            ]}
          />
        </div>
        <p className="muted">{t("ecarts_m11.mo.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m11.plans.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("ecarts_m11.plans.nouveau")}
              endpoint={`${BASE}/plans-sous-activite/`}
              fields={[
                { name: "budget", label: t("ecarts_m11.budget.budget"), type: "select", required: true, options: approuves.map((b) => ({ value: b.id, label: `${b.code} — ${b.label}` })) },
                { name: "actions", label: t("ecarts_m11.plans.actions"), type: "textarea", required: true },
                { name: "echeance", label: t("ecarts_m11.plans.echeance"), type: "date" },
              ]}
            />
          </SectionActions>
        }
      >
        <div data-testid="plans-sous-activite">
          <DataTable
            caption={t("ecarts_m11.plans.title")}
            rows={plans}
            columns={[
              { key: "plan", header: t("ecarts_m11.plans.plan"), render: (p) => `${p.code} · ${p.budget_code}`, sortValue: (p) => p.code },
              { key: "centre", header: t("ecarts_m11.plans.centre"), render: (p) => (p.centre ? `${p.centre} (${pct(p.taux)})` : "—") },
              { key: "actions", header: t("ecarts_m11.plans.actions"), render: (p) => p.actions },
              {
                key: "echeance",
                header: t("ecarts_m11.plans.echeance"),
                sortValue: (p) => p.echeance,
                render: (p) => (
                  <>
                    {formatDate(p.echeance)} {p.en_retard && <Badge tone="err">{t("ecarts_m11.plans.retard")}</Badge>}
                  </>
                ),
              },
              { key: "statut", header: t("ecarts_m11.plans.statut"), render: (p) => p.statut_label },
              actionsColumn<Plan>(t("ui.actions"), (p) =>
                p.statut === "clos"
                  ? []
                  : [
                      ...(p.statut === "ouvert" ? [{ label: t("ecarts_m11.plans.demarrer"), path: `${BASE}/plans-sous-activite/${p.id}/demarrer/`, tone: "ghost" as const }] : []),
                      { label: t("ecarts_m11.plans.clore"), path: `${BASE}/plans-sous-activite/${p.id}/clore/`, prompt: { name: "suivi", label: t("ecarts_m11.plans.suivi") } },
                    ],
              ),
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.reporting.title")}>
        <div className="field" style={{ maxWidth: "20rem" }}>
          <label htmlFor="m11-cloture">{t("ecarts_m11.reporting.cloture")}</label>
          <select id="m11-cloture" value={cloture} onChange={(e) => setCloture(e.target.value)}>
            <option value="">—</option>
            {clotures.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} · {c.period_label}
              </option>
            ))}
          </select>
        </div>
        {cloture && (
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost" onClick={() => download("j4")}>
              {t("ecarts_m11.reporting.pdfJ4")}
            </button>
            <button type="button" className="btn ghost" onClick={() => download("j6")}>
              {t("ecarts_m11.reporting.pdfJ6")}
            </button>
            <ActionBar
              actions={[
                { label: t("ecarts_m11.reporting.archiverJ4"), path: `${BASE}/reportings/archiver/`, body: { cloture, type: "j4" } },
                { label: t("ecarts_m11.reporting.archiverJ6"), path: `${BASE}/reportings/archiver/`, body: { cloture, type: "j6" } },
              ]}
            />
          </div>
        )}
        {dlError && (
          <p className="action-error" role="alert">
            {dlError}
          </p>
        )}
        <div data-testid="reportings-archives">
          <DataTable
            caption={t("ecarts_m11.reporting.title")}
            rows={reportings}
            columns={[
              { key: "cloture", header: t("ecarts_m11.reporting.cloture"), render: (r) => `${r.cloture_code} · ${r.period_label}`, sortValue: (r) => r.cloture_code },
              { key: "type", header: t("ecarts_m11.reporting.type"), render: (r) => t("ecarts_m11.reporting.horizon", { type: r.type_reporting === "j4" ? "J+4" : "J+6", n: r.horizon }) },
              { key: "echeance", header: t("ecarts_m11.reporting.echeance"), render: (r) => formatDate(r.echeance), sortValue: (r) => r.echeance },
              {
                key: "archive",
                header: t("ecarts_m11.reporting.archive"),
                sortValue: (r) => r.archive_le,
                render: (r) => (
                  <>
                    {formatDate(r.archive_le)} <Badge tone={r.a_temps ? "ok" : "err"}>{t(r.a_temps ? "ecarts_m11.reporting.aTemps" : "ecarts_m11.reporting.enRetard")}</Badge>
                  </>
                ),
              },
            ]}
          />
        </div>
        <p className="muted">{t("ecarts_m11.reporting.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m11.revue.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("ecarts_m11.revue.nouvelle")}
              endpoint={`${BASE}/revues-performance/`}
              fields={[
                { name: "period", label: t("ecarts_m11.budget.periode"), type: "select", required: true, options: optPeriode },
                { name: "date_revue", label: t("ecarts_m11.revue.date"), type: "date", required: true },
                { name: "participants", label: t("ecarts_m11.revue.participants") },
                { name: "ordre_du_jour", label: t("ecarts_m11.revue.odj"), type: "textarea" },
              ]}
            />
          </SectionActions>
        }
      >
        <div data-testid="revues-performance">
          <DataTable
            caption={t("ecarts_m11.revue.title")}
            rows={revues}
            columns={[
              {
                key: "revue",
                header: t("ecarts_m11.revue.revue"),
                sortValue: (r) => r.code,
                render: (r) => (
                  <>
                    {r.code} · {r.period_label} <Badge tone={r.statut === "tenue" ? "ok" : "warn"}>{r.statut_label}</Badge>
                  </>
                ),
              },
              { key: "date", header: t("ecarts_m11.revue.date"), render: (r) => formatDate(r.date_revue), sortValue: (r) => r.date_revue },
              { key: "odj", header: t("ecarts_m11.revue.odj"), render: (r) => <span style={{ whiteSpace: "pre-line" }}>{r.ordre_du_jour}</span> },
              { key: "decisions", header: t("ecarts_m11.revue.decisions"), render: (r) => r.decisions || "—" },
              actionsColumn<Revue>(t("ui.actions"), (r) =>
                r.statut === "planifiee"
                  ? [{ label: t("ecarts_m11.revue.tenir"), path: `${BASE}/revues-performance/${r.id}/tenir/`, prompt: { name: "decisions", label: t("ecarts_m11.revue.decisions") } }]
                  : [],
              ),
            ]}
          />
        </div>
        <p className="muted">{t("ecarts_m11.revue.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m11.fnp.title", { compte: apercu?.compte ?? "408" })}
        actions={
          <ActionBar actions={[{ label: t("ecarts_m11.fnp.provisionner"), path: `${BASE}/provisions-fnp/provisionner/`, body: { date_arrete: dateFnp }, confirm: t("ecarts_m11.fnp.confirm") }]} />
        }
      >
        <div className="field" style={{ maxWidth: "14rem" }}>
          <label htmlFor="m11-fnp-date">{t("ecarts_m11.fnp.date")}</label>
          <input id="m11-fnp-date" type="date" value={dateFnp} onChange={(e) => setDateFnp(e.target.value)} />
        </div>
        <div data-testid="fnp-apercu">
          <DataTable
            caption={t("tableaux.controleGestion.apercuFnp")}
            rows={withId(apercu?.lignes, (l) => `${l.bc}-${l.ligne}`)}
            emptyLabel={t("tableaux.controleGestion.aucuneFnp")}
            columns={[
              { key: "bc", header: t("ecarts_m11.fnp.bc"), render: (l) => `${l.bc} · ${l.ligne}`, sortValue: (l) => l.bc },
              { key: "fournisseur", header: t("ecarts_m11.fnp.fournisseur"), render: (l) => l.fournisseur },
              { key: "compte", header: t("ecarts_m11.fnp.compte"), render: (l) => l.compte },
              { key: "quantite", header: t("ecarts_m11.fnp.quantite"), num: true, render: (l) => formatNumber(Number(l.quantite), { decimals: Number.isInteger(Number(l.quantite)) ? 0 : 2 }) },
              { key: "montant", header: t("ecarts_m11.fnp.montant"), num: true, render: (l) => money(l.montant), sortValue: (l) => Number(l.montant ?? 0) },
            ]}
          />
        </div>
        <p>
          <strong>{t("ecarts_m11.fnp.total")}</strong> : <span className="amount">{money(apercu?.total)}</span>
        </p>
        <div data-testid="fnp-provisions">
          <DataTable
            caption={t("tableaux.controleGestion.provisions")}
            rows={fnps}
            emptyLabel={t("tableaux.controleGestion.aucuneProvision")}
            columns={[
              { key: "provision", header: t("tableaux.controleGestion.provision"), render: (p) => `${p.code} · ${formatDate(p.date_arrete)}`, sortValue: (p) => p.date_arrete },
              { key: "montant", header: t("tableaux.controleGestion.montant"), num: true, render: (p) => money(p.montant) },
              {
                key: "statut",
                header: t("tableaux.controleGestion.statut"),
                render: (p) => (
                  <>
                    {p.statut_label} <span className="muted">{p.move_number ?? ""} {p.extourne_number ? `→ ${p.extourne_number}` : ""}</span>
                  </>
                ),
              },
              actionsColumn<Fnp>(t("ui.actions"), (p) =>
                p.statut === "comptabilisee" ? [{ label: t("ecarts_m11.fnp.extourner"), path: `${BASE}/provisions-fnp/${p.id}/extourner/`, tone: "ghost" as const }] : [],
              ),
            ]}
          />
        </div>
        <p className="muted">{t("ecarts_m11.fnp.note")}</p>
      </SectionCard>
    </>
  );
}
