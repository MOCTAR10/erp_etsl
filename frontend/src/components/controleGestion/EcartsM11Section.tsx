import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

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

const money = (v: string | null | undefined) => (v === null || v === undefined ? "••••••" : `${formatNumber(Number(v))} F`);
const pct = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${formatNumber(Number(v))} %`);
const BASE = "/api/controle-gestion";

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

/** Table de paramétrage (RGM_*, KPI_CIBLES) : valeurs ETSL modifiables et confirmables, provisoires par défaut. */
function ParamTable({ table, title }: { table: string; title: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const rows = useList<Param>(["params", table], `${BASE}/parametres/?table=${table}`);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const done = { onSuccess: () => { setEdit(null); setError(null); void qc.invalidateQueries(); }, onError: (e: unknown) => setError(describeError(e)) };
  const save = useMutation({ mutationFn: (v: { id: string; valeur: string }) => api.patch(`${BASE}/parametres/${v.id}/`, { valeur: v.valeur }), ...done });
  const confirm = useMutation({ mutationFn: (id: string) => api.post(`${BASE}/parametres/${id}/confirmer/`), ...done });
  return (
    <>
      <h3>
        {title} <code>{table}</code>
      </h3>
      <table className="table" data-testid={`table-${table}`}>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td>{p.label}</td>
              <td>
                {edit?.id === p.id ? (
                  <input aria-label={p.label} type="number" step="0.01" value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                ) : (
                  `${formatNumber(Number(p.valeur))} ${p.unite}`
                )}
              </td>
              <td>{p.est_provisoire ? <Badge tone="warn">{t("ecarts_m11.provisoire")}</Badge> : <Badge tone="ok">{t("ecarts_m11.confirme")}</Badge>}</td>
              <td>
                {edit?.id === p.id ? (
                  <button type="button" className="btn primary" onClick={() => save.mutate(edit)}>
                    {t("ecarts_m11.enregistrer")}
                  </button>
                ) : (
                  <>
                    <button type="button" className="btn ghost" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>
                      {t("ecarts_m11.modifier")}
                    </button>
                    {p.est_provisoire && (
                      <button type="button" className="btn ghost" onClick={() => confirm.mutate(p.id)}>
                        {t("ecarts_m11.confirmer")}
                      </button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
          <table className="table">
            <tbody>
              {budget.lignes.map((l) => (
                <tr key={l.id}>
                  <td>{l.period_label}</td>
                  <td>{money(l.montant)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => {
                        const v = window.prompt(t("ecarts_m11.edition.nouveauMontant"), l.montant ?? "");
                        if (v !== null) saveLigne.mutate({ id: l.id, montant: v });
                      }}
                    >
                      {t("ecarts_m11.modifier")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

/** Écarts M11 : révision par ligne, tables RGM, axes, pipe → budget, imputation de structure, KPI, tableaux de bord,
 *  marge d'affaire, coût MO, plans d'action, reporting archivé, revue P-M11.10, provision 408. */
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

  return (
    <>
      <SectionCard title={t("ecarts_m11.budget.title")}>
        <EditionBrouillon budgets={budgets} />
        <h3>{t("ecarts_m11.budget.revisionLigne")}</h3>
        <div className="action-bar-buttons">
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
        </div>
        {revLignes.length > 0 && (
          <table className="table" data-testid="revision-lignes">
            <thead>
              <tr>
                <th>{t("ecarts_m11.budget.revision")}</th>
                <th>{t("ecarts_m11.budget.periode")}</th>
                <th>{t("ecarts_m11.budget.avant")}</th>
                <th>{t("ecarts_m11.budget.apres")}</th>
              </tr>
            </thead>
            <tbody>
              {revLignes.map((l) => (
                <tr key={l.id}>
                  <td>{l.revision_code}</td>
                  <td>{l.period_label}</td>
                  <td>{money(l.ancien_montant)}</td>
                  <td>{money(l.nouveau_montant)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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

      <SectionCard title={t("ecarts_m11.axes.title")}>
        <div className="action-bar-buttons">
          <ActionBar actions={[{ label: t("ecarts_m11.axes.initialiser"), path: `${BASE}/axes/initialiser/`, tone: "ghost" }]} />
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
        </div>
        <table className="table" data-testid="axes-analytiques">
          <thead>
            <tr>
              <th>{t("ecarts_m11.axes.axe")}</th>
              <th>{t("ecarts_m11.axes.type")}</th>
              <th>{t("ecarts_m11.axes.valeurs")}</th>
            </tr>
          </thead>
          <tbody>
            {axes.map((a) => (
              <tr key={a.id}>
                <td>
                  {a.code} — {a.label}
                </td>
                <td>{a.axis_type_label}</td>
                <td>
                  {valeurs
                    .filter((v) => v.axis_code === a.code)
                    .map((v) => v.code)
                    .join(", ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m11.axes.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.pipe.title")}>
        <Provisoire show={pipe?.provisoire} />
        <table className="table" data-testid="pipe-budget">
          <thead>
            <tr>
              <th>{t("ecarts_m11.pipe.categorie")}</th>
              <th>{t("ecarts_m11.pipe.nb")}</th>
              <th>{t("ecarts_m11.pipe.brut")}</th>
              <th>{t("ecarts_m11.pipe.ponderation")}</th>
              <th>{t("ecarts_m11.pipe.pondere")}</th>
            </tr>
          </thead>
          <tbody>
            {(pipe?.categories ?? []).map((c) => (
              <tr key={c.categorie}>
                <td>{t(`ecarts_m11.pipe.cat.${c.categorie}`)}</td>
                <td>{c.nb}</td>
                <td>{money(c.brut)}</td>
                <td>{pct(c.ponderation)}</td>
                <td>{money(c.pondere)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          <strong>{t("ecarts_m11.pipe.total")}</strong> : {money(pipe?.total)}
        </p>
        <ActionBar actions={[{ label: t("ecarts_m11.pipe.proposer"), path: `${BASE}/pipe-budget/proposer/`, body: { fiscal_year: fiscalYear }, confirm: t("ecarts_m11.pipe.confirm") }]} />
      </SectionCard>

      <SectionCard title={t("ecarts_m11.imputation.title")}>
        <Provisoire show={imputation?.provisoire} />
        <p>
          {t("ecarts_m11.imputation.cle")} : <strong>{imputation?.cle_label ?? "—"}</strong> · {t("ecarts_m11.imputation.structure")} : {money(imputation?.charges_structure)}
        </p>
        <table className="table" data-testid="imputation-structure">
          <thead>
            <tr>
              <th>{t("ecarts_m11.col.affaire")}</th>
              <th>{t("ecarts_m11.col.profil")}</th>
              <th>{t("ecarts_m11.imputation.part")}</th>
              <th>{t("ecarts_m11.col.produits")}</th>
              <th>{t("ecarts_m11.imputation.margeDirecte")}</th>
              <th>{t("ecarts_m11.imputation.imputee")}</th>
              <th>{t("ecarts_m11.imputation.margeApres")}</th>
              <th>{t("ecarts_m11.imputation.tauxReel")}</th>
              <th>{t("ecarts_m11.imputation.tauxStandard")}</th>
            </tr>
          </thead>
          <tbody>
            {(imputation?.rows ?? []).map((r) => (
              <tr key={r.affaire}>
                <td>
                  {r.code} · {r.titre}
                </td>
                <td>{r.profil}</td>
                <td>{pct(r.part_pct)}</td>
                <td>{money(r.produits)}</td>
                <td>{money(r.marge_directe)}</td>
                <td>{money(r.structure_imputee)}</td>
                <td>{money(r.marge_apres_structure)}</td>
                <td>{pct(r.taux_structure_reel)}</td>
                <td>{pct(r.taux_structure_standard)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.kpi.title")}>
        <Provisoire show={Boolean(kpis)} />
        <table className="table" data-testid="kpis-m11">
          <thead>
            <tr>
              <th>{t("ecarts_m11.kpi.code")}</th>
              <th>{t("ecarts_m11.kpi.libelle")}</th>
              <th>{t("ecarts_m11.kpi.valeur")}</th>
              <th>{t("ecarts_m11.kpi.cible")}</th>
              <th>{t("ecarts_m11.kpi.formule")}</th>
            </tr>
          </thead>
          <tbody>
            {(kpis?.kpis ?? []).map((k) => (
              <tr key={k.code}>
                <td>{k.code}</td>
                <td>{k.libelle}</td>
                <td>
                  {k.valeur === null ? "—" : `${formatNumber(Number(k.valeur))} ${k.unite}`}{" "}
                  {k.atteint !== null && <Badge tone={k.atteint ? "ok" : "err"}>{t(k.atteint ? "ecarts_m11.kpi.atteint" : "ecarts_m11.kpi.nonAtteint")}</Badge>}
                </td>
                <td>{`${formatNumber(Number(k.cible))} ${k.unite}`}</td>
                <td className="muted">{k.formule}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m11.kpi.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.tableau.title")}>
        <div className="field" style={{ maxWidth: "16rem" }}>
          <label htmlFor="m11-par">{t("ecarts_m11.tableau.par")}</label>
          <select id="m11-par" value={par} onChange={(e) => setPar(e.target.value)}>
            {["profil", "client", "affaire", "responsable"].map((p) => (
              <option key={p} value={p}>
                {t(`ecarts_m11.tableau.axes.${p}`)}
              </option>
            ))}
          </select>
        </div>
        <table className="table" data-testid="tableau-bord-m11">
          <thead>
            <tr>
              <th>{t(`ecarts_m11.tableau.axes.${par}`)}</th>
              <th>{t("ecarts_m11.tableau.affaires")}</th>
              <th>{t("ecarts_m11.tableau.caPrevu")}</th>
              <th>{t("ecarts_m11.tableau.margePrevue")}</th>
              <th>{t("ecarts_m11.col.produits")}</th>
              <th>{t("ecarts_m11.tableau.charges")}</th>
              <th>{t("ecarts_m11.tableau.coutGr")}</th>
              <th>{t("ecarts_m11.tableau.margeReelle")}</th>
            </tr>
          </thead>
          <tbody>
            {(tableau?.lignes ?? []).map((l) => (
              <tr key={l.cle}>
                <td>{l.cle}</td>
                <td>{l.affaires}</td>
                <td>{money(l.ca_prevu)}</td>
                <td>{money(l.marge_prevue)}</td>
                <td>{money(l.produits)}</td>
                <td>{money(l.charges)}</td>
                <td>{money(l.cout_gr)}</td>
                <td>{money(l.marge_reelle)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.marges.title")}>
        <table className="table" data-testid="marges-affaires">
          <thead>
            <tr>
              <th>{t("ecarts_m11.col.affaire")}</th>
              <th>{t("ecarts_m11.col.client")}</th>
              <th>{t("ecarts_m11.col.profil")}</th>
              <th>{t("ecarts_m11.marges.ca")}</th>
              <th>{t("ecarts_m11.marges.marge")}</th>
              <th>{t("ecarts_m11.marges.validation")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(marges?.rows ?? []).map((m) => (
              <tr key={m.affaire}>
                <td>
                  {m.code} · {m.titre}
                </td>
                <td>{m.client || "—"}</td>
                <td>{m.profil}</td>
                <td>{money(m.ca)}</td>
                <td>
                  {money(m.marge)} ({pct(m.taux)})
                </td>
                <td>
                  <Badge tone={m.validation === "validee" ? "ok" : m.validation === "rejetee" ? "err" : "warn"}>{t(`ecarts_m11.marges.statuts.${m.validation}`)}</Badge>
                  {m.valide_par ? ` ${m.valide_par}` : ""}
                </td>
                <td>
                  <ActionBar
                    actions={[
                      { label: t("ecarts_m11.marges.valider"), path: `${BASE}/marges-affaires/${m.affaire}/valider/` },
                      { label: t("ecarts_m11.marges.rejeter"), path: `${BASE}/marges-affaires/${m.affaire}/rejeter/`, tone: "danger" as const, prompt: { name: "commentaire", label: t("ecarts_m11.marges.motif") } },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.mo.title")}>
        <table className="table" data-testid="cout-mo-affaires">
          <thead>
            <tr>
              <th>{t("ecarts_m11.col.affaire")}</th>
              <th>{t("ecarts_m11.mo.ordres")}</th>
              <th>{t("ecarts_m11.mo.heures")}</th>
              <th>{t("ecarts_m11.mo.nonValorisees")}</th>
              <th>{t("ecarts_m11.mo.cout")}</th>
              <th>{t("ecarts_m11.mo.coutHoraire")}</th>
            </tr>
          </thead>
          <tbody>
            {(coutMo?.rows ?? []).map((r) => (
              <tr key={r.affaire}>
                <td>{r.affaire}</td>
                <td>{r.ordres}</td>
                <td>{formatNumber(Number(r.heures))} h</td>
                <td>{formatNumber(Number(r.heures_non_valorisees))} h</td>
                <td>{money(r.cout)}</td>
                <td>{money(r.cout_horaire_moyen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m11.mo.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.plans.title")}>
        <QuickForm
          title={t("ecarts_m11.plans.nouveau")}
          endpoint={`${BASE}/plans-sous-activite/`}
          fields={[
            { name: "budget", label: t("ecarts_m11.budget.budget"), type: "select", required: true, options: approuves.map((b) => ({ value: b.id, label: `${b.code} — ${b.label}` })) },
            { name: "actions", label: t("ecarts_m11.plans.actions"), type: "textarea", required: true },
            { name: "echeance", label: t("ecarts_m11.plans.echeance"), type: "date" },
          ]}
        />
        <table className="table" data-testid="plans-sous-activite">
          <thead>
            <tr>
              <th>{t("ecarts_m11.plans.plan")}</th>
              <th>{t("ecarts_m11.plans.centre")}</th>
              <th>{t("ecarts_m11.plans.actions")}</th>
              <th>{t("ecarts_m11.plans.echeance")}</th>
              <th>{t("ecarts_m11.plans.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.code} · {p.budget_code}
                </td>
                <td>{p.centre ? `${p.centre} (${pct(p.taux)})` : "—"}</td>
                <td>{p.actions}</td>
                <td>
                  {p.echeance ?? "—"} {p.en_retard && <Badge tone="err">{t("ecarts_m11.plans.retard")}</Badge>}
                </td>
                <td>{p.statut_label}</td>
                <td>
                  {p.statut !== "clos" && (
                    <ActionBar
                      actions={[
                        ...(p.statut === "ouvert" ? [{ label: t("ecarts_m11.plans.demarrer"), path: `${BASE}/plans-sous-activite/${p.id}/demarrer/`, tone: "ghost" as const }] : []),
                        { label: t("ecarts_m11.plans.clore"), path: `${BASE}/plans-sous-activite/${p.id}/clore/`, prompt: { name: "suivi", label: t("ecarts_m11.plans.suivi") } },
                      ]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
        <table className="table" data-testid="reportings-archives">
          <thead>
            <tr>
              <th>{t("ecarts_m11.reporting.cloture")}</th>
              <th>{t("ecarts_m11.reporting.type")}</th>
              <th>{t("ecarts_m11.reporting.echeance")}</th>
              <th>{t("ecarts_m11.reporting.archive")}</th>
            </tr>
          </thead>
          <tbody>
            {reportings.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.cloture_code} · {r.period_label}
                </td>
                <td>{t("ecarts_m11.reporting.horizon", { type: r.type_reporting === "j4" ? "J+4" : "J+6", n: r.horizon })}</td>
                <td>{r.echeance}</td>
                <td>
                  {r.archive_le} <Badge tone={r.a_temps ? "ok" : "err"}>{t(r.a_temps ? "ecarts_m11.reporting.aTemps" : "ecarts_m11.reporting.enRetard")}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m11.reporting.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.revue.title")}>
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
        <table className="table" data-testid="revues-performance">
          <thead>
            <tr>
              <th>{t("ecarts_m11.revue.revue")}</th>
              <th>{t("ecarts_m11.revue.date")}</th>
              <th>{t("ecarts_m11.revue.odj")}</th>
              <th>{t("ecarts_m11.revue.decisions")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {revues.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.code} · {r.period_label} <Badge tone={r.statut === "tenue" ? "ok" : "warn"}>{r.statut_label}</Badge>
                </td>
                <td>{r.date_revue}</td>
                <td style={{ whiteSpace: "pre-line" }}>{r.ordre_du_jour}</td>
                <td>{r.decisions || "—"}</td>
                <td>
                  {r.statut === "planifiee" && (
                    <ActionBar actions={[{ label: t("ecarts_m11.revue.tenir"), path: `${BASE}/revues-performance/${r.id}/tenir/`, prompt: { name: "decisions", label: t("ecarts_m11.revue.decisions") } }]} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m11.revue.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m11.fnp.title", { compte: apercu?.compte ?? "408" })}>
        <div className="field" style={{ maxWidth: "14rem" }}>
          <label htmlFor="m11-fnp-date">{t("ecarts_m11.fnp.date")}</label>
          <input id="m11-fnp-date" type="date" value={dateFnp} onChange={(e) => setDateFnp(e.target.value)} />
        </div>
        <table className="table" data-testid="fnp-apercu">
          <thead>
            <tr>
              <th>{t("ecarts_m11.fnp.bc")}</th>
              <th>{t("ecarts_m11.fnp.fournisseur")}</th>
              <th>{t("ecarts_m11.fnp.compte")}</th>
              <th>{t("ecarts_m11.fnp.quantite")}</th>
              <th>{t("ecarts_m11.fnp.montant")}</th>
            </tr>
          </thead>
          <tbody>
            {(apercu?.lignes ?? []).map((l) => (
              <tr key={`${l.bc}-${l.ligne}`}>
                <td>
                  {l.bc} · {l.ligne}
                </td>
                <td>{l.fournisseur}</td>
                <td>{l.compte}</td>
                <td>{l.quantite}</td>
                <td>{money(l.montant)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          <strong>{t("ecarts_m11.fnp.total")}</strong> : {money(apercu?.total)}
        </p>
        <ActionBar actions={[{ label: t("ecarts_m11.fnp.provisionner"), path: `${BASE}/provisions-fnp/provisionner/`, body: { date_arrete: dateFnp }, confirm: t("ecarts_m11.fnp.confirm") }]} />
        <table className="table" data-testid="fnp-provisions">
          <tbody>
            {fnps.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.code} · {p.date_arrete}
                </td>
                <td>{money(p.montant)}</td>
                <td>
                  {p.statut_label} {p.move_number ?? ""} {p.extourne_number ? `→ ${p.extourne_number}` : ""}
                </td>
                <td>{p.statut === "comptabilisee" && <ActionBar actions={[{ label: t("ecarts_m11.fnp.extourner"), path: `${BASE}/provisions-fnp/${p.id}/extourner/`, tone: "ghost" as const }]} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m11.fnp.note")}</p>
      </SectionCard>
    </>
  );
}
