import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { ActionBar, Badge, DataTable, Kpi, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

/** Écarts M1 : paramètres provisoires, scoring 360°, alertes et échéances, pipe par profil, chiffrage et dérive,
 *  profils contractuels, habilitations, RAO / RC archivés, indicateurs commerciaux. */

interface Parametre {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  statut_valeur: string;
  est_provisoire: boolean;
}
interface Signal {
  code: string;
  libelle: string;
}
interface ClientSignal {
  id: string;
  client: string;
  segment: string;
  score_enregistre: number;
  score_calcule: number;
  dernier_contact: string | null;
  signaux: Signal[];
}
interface Vue360 {
  client: string;
  scoring: { score: number; composantes: { critere: string; poids: string; note: string }[] };
  signaux: Signal[];
  opportunites: unknown[];
  offres: unknown[];
  affaires: unknown[];
  contrats: unknown[];
}
interface AlerteOpp {
  id: string;
  code: string;
  objet: string;
  etape: string;
  client: string | null;
  motifs: string[];
}
interface Echeance {
  type: string;
  id: string;
  code: string;
  libelle: string;
  date_echeance: string;
  jours: number;
  palier: string | null;
}
interface LigneProfil {
  profil: string;
  libelle: string;
  nombre: number;
  montant: string | null;
  pondere: string | null;
  gagnees: number;
  perdues: number;
  conversion_pct: string | null;
}
interface Indicateurs {
  prix_moyen: string | null;
  offres_gagnees: number;
  taux_transformation_pct: string | null;
  score_moyen: string | null;
  clients_sous_seuil: number;
  definition_prix_moyen: string;
}
interface OffreCourte {
  id: string;
  code: string;
  version: number;
  title: string;
}
interface Structure {
  taux: Record<string, string>;
  taux_provisoires: boolean;
  par_nature: { nature: string; libelle: string; montant: string | null }[];
  par_lot: { lot: string; montant: string | null }[];
  debourse_sec: string | null;
  frais_indirects: string | null;
  aleas: string | null;
  prix_revient: string | null;
  prix_vente_cible: string | null;
  prix_offre: string | null;
  marge_offre: string | null;
  taux_marge_offre_pct: string | null;
  sous_marge_cible: boolean;
}
interface Derive {
  id: string;
  code: string;
  titre: string;
  statut: string;
  avancement_pct: string;
  cout_prevu_a_date: string | null;
  cout_reel: string | null;
  derive_pct: string | null;
  alerte: boolean;
}
interface ContratCourt {
  id: string;
  code: string;
  profile_label: string;
  status: string;
  alerte_duree: string | null;
}
interface Calculs {
  taux_retenue_pct: string;
  retenue_garantie: string | null;
  net_apres_retenue: string | null;
  penalites: string | null;
  penalites_plafonnees: boolean;
  indexation: { coefficient: string; montant_indexe: string | null } | null;
  duree_mois: number | null;
  alerte_duree: string | null;
  controle_profil: string[];
  provisoire: boolean;
}
interface Retenues {
  retenue_cumulee: string | null;
  base_facturee: string | null;
  date_liberation: string | null;
}
interface Habilitations {
  habilitations_requises: string[];
  personnel: { matricule: string; nom: string; equipe: string; manquantes: string[]; conforme: boolean }[];
  conforme: boolean;
}
interface Rao {
  id: string;
  tender_ref: string;
  score: string | null;
  decision_rao: string;
  review_status_label: string;
  document: string | null;
}
interface Rc {
  id: string;
  affaire_code: string;
  type_label: string;
  statut_label: string;
  document: string | null;
}

const NATURES = ["fourniture", "main_oeuvre", "sous_traitance", "equipement", "frais_directs"];
const PROFILS = ["marche_travaux", "maintenance"];
const montant = (v: string | null | undefined) => (v === null || v === undefined ? "••••" : formatNumber(v));
const liste = <T,>(path: string) => () => api.listAll<T>(path);

function ParametresM1() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const params = useQuery({ queryKey: ["m1", "parametres"], queryFn: liste<Parametre>("/api/commercial/parametres/"), retry: 0 });
  const [saisie, setSaisie] = useState<Record<string, string>>({});
  const [erreur, setErreur] = useState<string | null>(null);
  const done = () => {
    setErreur(null);
    void qc.invalidateQueries({ queryKey: ["m1"] });
  };
  const enregistrer = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/commercial/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: done,
    onError: () => setErreur(t("ecarts_m1.params.erreur")),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/commercial/parametres/${id}/confirmer/`),
    onSuccess: done,
    onError: () => setErreur(t("ecarts_m1.params.erreurConfirmer")),
  });
  const lignes = params.data ?? [];
  const provisoires = lignes.filter((p) => p.est_provisoire).length;
  return (
    <SectionCard title={t("ecarts_m1.params.title")}>
      {provisoires > 0 && (
        <p className="action-error" role="note" data-testid="alerte-provisoire-m1">
          {t("ecarts_m1.params.warn", { count: provisoires })}
        </p>
      )}
      {erreur && <p className="action-error">{erreur}</p>}
      <div className="table-wrap">
        <table className="table" data-testid="parametres-m1">
          <thead>
            <tr>
              <th>{t("ecarts_m1.params.libelle")}</th>
              <th>{t("ecarts_m1.params.valeur")}</th>
              <th>{t("ecarts_m1.params.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lignes.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.label} <span className="muted">({p.code})</span>
                </td>
                <td>
                  <input
                    className="field"
                    style={{ width: "7rem" }}
                    aria-label={p.label}
                    value={saisie[p.id] ?? p.valeur}
                    onChange={(e) => setSaisie({ ...saisie, [p.id]: e.target.value })}
                  />{" "}
                  {p.unite}
                </td>
                <td>
                  <Badge tone={p.est_provisoire ? "warn" : "ok"}>{t(`ecarts_m1.params.${p.statut_valeur}`)}</Badge>
                </td>
                <td>
                  <div className="action-bar-buttons">
                    {saisie[p.id] !== undefined && saisie[p.id] !== p.valeur && (
                      <button type="button" className="btn" onClick={() => enregistrer.mutate({ id: p.id, valeur: saisie[p.id] })}>
                        {t("ecarts_m1.params.enregistrer")}
                      </button>
                    )}
                    {p.est_provisoire && (
                      <button type="button" className="btn ghost" onClick={() => confirmer.mutate(p.id)}>
                        {t("ecarts_m1.params.confirmer")}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function Clients360() {
  const { t } = useTranslation();
  const [client, setClient] = useState("");
  const signaux = useQuery({
    queryKey: ["m1", "signaux"],
    queryFn: () => api.get<{ lignes: ClientSignal[]; provisoire: boolean }>("/api/commercial/profiles/signaux/"),
    retry: 0,
  });
  const vue = useQuery({
    queryKey: ["m1", "vue360", client],
    queryFn: () => api.get<Vue360>(`/api/commercial/profiles/${client}/vue-360/`),
    enabled: !!client,
    retry: 0,
  });
  const cols: Column<ClientSignal>[] = [
    { key: "client", header: t("ecarts_m1.clients.client"), render: (c) => c.client },
    { key: "segment", header: t("ecarts_m1.clients.segment"), render: (c) => c.segment },
    { key: "score", header: t("ecarts_m1.clients.score"), num: true, render: (c) => `${c.score_calcule} (${c.score_enregistre})` },
    { key: "contact", header: t("ecarts_m1.clients.dernierContact"), render: (c) => (c.dernier_contact ? formatDate(c.dernier_contact) : "—") },
    {
      key: "signaux",
      header: t("ecarts_m1.clients.signaux"),
      render: (c) =>
        c.signaux.length ? c.signaux.map((s) => <Badge key={s.code} tone="warn">{s.libelle}</Badge>) : <Badge tone="ok">{t("ecarts_m1.clients.ras")}</Badge>,
    },
  ];
  const lignes = signaux.data?.lignes ?? [];
  return (
    <SectionCard title={t("ecarts_m1.clients.title")}>
      <ActionBar actions={[{ label: t("ecarts_m1.clients.recalculer"), path: "/api/commercial/profiles/recalculer-scores/" }]} />
      {signaux.data?.provisoire && <p className="muted">{t("ecarts_m1.provisoireNote")}</p>}
      <DataTable rows={lignes} columns={cols} caption={t("ecarts_m1.clients.title")} />
      <label className="field" style={{ marginTop: "0.5rem" }}>
        {t("ecarts_m1.clients.vue360")}
        <select value={client} onChange={(e) => setClient(e.target.value)} aria-label={t("ecarts_m1.clients.vue360")}>
          <option value="">—</option>
          {lignes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.client}
            </option>
          ))}
        </select>
      </label>
      {vue.data && (
        <div data-testid="vue-360">
          <p>
            <strong>{vue.data.client}</strong> · {t("ecarts_m1.clients.score")} {vue.data.scoring.score}/100 ·{" "}
            {t("ecarts_m1.clients.compte", {
              opp: vue.data.opportunites.length,
              offres: vue.data.offres.length,
              affaires: vue.data.affaires.length,
              contrats: vue.data.contrats.length,
            })}
          </p>
          <DataTable
            rows={vue.data.scoring.composantes.map((c) => ({ ...c, id: c.critere }))}
            caption={t("ecarts_m1.clients.composantes")}
            columns={[
              { key: "c", header: t("ecarts_m1.clients.critere"), render: (c) => t(`ecarts_m1.clients.criteres.${c.critere}`) },
              { key: "p", header: t("ecarts_m1.clients.poids"), num: true, render: (c) => c.poids },
              { key: "n", header: t("ecarts_m1.clients.note"), num: true, render: (c) => c.note },
            ]}
          />
        </div>
      )}
    </SectionCard>
  );
}

function AlertesEcheances() {
  const { t } = useTranslation();
  const opp = useQuery({
    queryKey: ["m1", "alertes"],
    queryFn: () => api.get<{ lignes: AlerteOpp[]; jours: string }>("/api/commercial/opportunities/alertes/"),
    retry: 0,
  });
  const ech = useQuery({
    queryKey: ["m1", "echeances"],
    queryFn: () => api.get<{ lignes: (Echeance & { cle?: string })[]; paliers: number[]; provisoire: boolean }>("/api/commercial/pilotage/echeances/"),
    retry: 0,
  });
  return (
    <SectionCard title={t("ecarts_m1.alertes.title")}>
      <ActionBar actions={[{ label: t("ecarts_m1.alertes.relancer"), path: "/api/commercial/pilotage/relancer/" }]} />
      <h4>{t("ecarts_m1.alertes.opportunites", { jours: opp.data?.jours ?? "" })}</h4>
      <DataTable
        rows={opp.data?.lignes ?? []}
        caption={t("ecarts_m1.alertes.opportunites", { jours: opp.data?.jours ?? "" })}
        columns={[
          { key: "code", header: t("commercial.col.code"), render: (o) => o.code },
          { key: "objet", header: t("commercial.col.titre"), render: (o) => o.objet },
          { key: "etape", header: t("ecarts_m1.alertes.etape"), render: (o) => o.etape },
          { key: "client", header: t("commercial.col.client"), render: (o) => o.client ?? "—" },
          { key: "motifs", header: t("ecarts_m1.alertes.motifs"), render: (o) => o.motifs.join(" · ") },
        ]}
      />
      <h4>{t("ecarts_m1.alertes.echeances", { paliers: (ech.data?.paliers ?? []).filter((p) => p > 0).map((p) => `J-${p}`).join(" / ") })}</h4>
      {ech.data?.provisoire && <p className="muted">{t("ecarts_m1.provisoireNote")}</p>}
      <DataTable
        rows={(ech.data?.lignes ?? []).map((e) => ({ ...e, id: `${e.type}-${e.id}` }))}
        caption={t("ecarts_m1.alertes.echeancesCaption")}
        columns={[
          { key: "type", header: t("ecarts_m1.alertes.type"), render: (e) => t(`ecarts_m1.alertes.types.${e.type}`) },
          { key: "code", header: t("commercial.col.code"), render: (e) => e.code },
          { key: "lib", header: t("ecarts_m1.alertes.objet"), render: (e) => e.libelle },
          { key: "date", header: t("ecarts_m1.alertes.date"), render: (e) => formatDate(e.date_echeance) },
          {
            key: "palier",
            header: t("ecarts_m1.alertes.palier"),
            render: (e) => <Badge tone={e.jours <= 30 ? "err" : e.jours <= 60 ? "warn" : "brand"}>{e.palier ?? "—"}</Badge>,
          },
        ]}
      />
    </SectionCard>
  );
}

function PipeProfilIndicateurs() {
  const { t } = useTranslation();
  const profils = useQuery({
    queryKey: ["m1", "pipe-profil"],
    queryFn: () => api.get<{ lignes: LigneProfil[] }>("/api/commercial/opportunities/pipe-par-profil/"),
    retry: 0,
  });
  const ind = useQuery({ queryKey: ["m1", "indicateurs"], queryFn: () => api.get<Indicateurs>("/api/commercial/pilotage/indicateurs/"), retry: 0 });
  const i = ind.data;
  return (
    <SectionCard title={t("ecarts_m1.profil.title")}>
      {i && (
        <div className="kpi-grid">
          <Kpi label={t("ecarts_m1.indic.prixMoyen")} value={montant(i.prix_moyen)} hint={i.definition_prix_moyen} tone="brand" />
          <Kpi label={t("ecarts_m1.indic.transformation")} value={i.taux_transformation_pct === null ? "—" : `${i.taux_transformation_pct} %`} tone="accent" />
          <Kpi label={t("ecarts_m1.indic.scoreMoyen")} value={i.score_moyen ?? "—"} tone="ok" />
          <Kpi label={t("ecarts_m1.indic.sousSeuil")} value={i.clients_sous_seuil} tone="warn" />
        </div>
      )}
      <DataTable
        rows={(profils.data?.lignes ?? []).map((l) => ({ ...l, id: l.profil }))}
        caption={t("ecarts_m1.profil.title")}
        columns={[
          { key: "p", header: t("ecarts_m1.profil.profil"), render: (l) => l.libelle },
          { key: "n", header: t("ecarts_m1.profil.nombre"), num: true, render: (l) => l.nombre },
          { key: "m", header: t("ecarts_m1.profil.montant"), num: true, render: (l) => montant(l.montant) },
          { key: "pp", header: t("ecarts_m1.profil.pondere"), num: true, render: (l) => montant(l.pondere) },
          { key: "g", header: t("ecarts_m1.profil.gagneesPerdues"), num: true, render: (l) => `${l.gagnees} / ${l.perdues}` },
          { key: "c", header: t("ecarts_m1.profil.conversion"), num: true, render: (l) => (l.conversion_pct === null ? "—" : `${l.conversion_pct} %`) },
        ]}
      />
    </SectionCard>
  );
}

function Chiffrage() {
  const { t } = useTranslation();
  const [offre, setOffre] = useState("");
  const offres = useQuery({ queryKey: ["m1", "offres"], queryFn: liste<OffreCourte>("/api/commercial/estimates/"), retry: 0 });
  const st = useQuery({
    queryKey: ["m1", "structure", offre],
    queryFn: () => api.get<Structure>(`/api/commercial/estimates/${offre}/structure/`),
    enabled: !!offre,
    retry: 0,
  });
  const derives = useQuery({
    queryKey: ["m1", "derives"],
    queryFn: () => api.get<{ lignes: Derive[]; seuil_pct: string; provisoire: boolean }>("/api/commercial/affaires/derives/"),
    retry: 0,
  });
  const s = st.data;
  const lignes: { id: string; poste: string; montant: string | null }[] = s
    ? [
        ...s.par_nature.map((n) => ({ id: `n-${n.nature}`, poste: n.libelle, montant: n.montant })),
        { id: "ds", poste: t("ecarts_m1.chiffrage.debourse"), montant: s.debourse_sec },
        { id: "fi", poste: `${t("ecarts_m1.chiffrage.fi")} (${s.taux.frais_indirects} %)`, montant: s.frais_indirects },
        { id: "al", poste: `${t("ecarts_m1.chiffrage.aleas")} (${s.taux.aleas} %)`, montant: s.aleas },
        { id: "pr", poste: t("ecarts_m1.chiffrage.pr"), montant: s.prix_revient },
        { id: "pv", poste: `${t("ecarts_m1.chiffrage.pv")} (${s.taux.marge} %)`, montant: s.prix_vente_cible },
        { id: "po", poste: t("ecarts_m1.chiffrage.prixOffre"), montant: s.prix_offre },
        { id: "mo", poste: `${t("ecarts_m1.chiffrage.margeOffre")} (${s.taux_marge_offre_pct ?? "—"} %)`, montant: s.marge_offre },
      ]
    : [];
  return (
    <SectionCard title={t("ecarts_m1.chiffrage.title")}>
      <div className="action-bar-buttons">
        <QuickForm
          title={t("ecarts_m1.chiffrage.ajouterLigne")}
          endpoint="/api/commercial/estimate-lines/"
          fields={[
            { name: "estimate", label: t("ecarts_m1.chiffrage.offre"), type: "select", required: true, options: (offres.data ?? []).map((o) => ({ value: o.id, label: `${o.code} v${o.version} · ${o.title}` })) },
            { name: "lot", label: t("ecarts_m1.chiffrage.lot") },
            { name: "label", label: t("ecarts_m1.chiffrage.designation"), required: true },
            { name: "nature", label: t("ecarts_m1.chiffrage.nature"), type: "select", options: NATURES.map((n) => ({ value: n, label: t(`ecarts_m1.natures.${n}`) })) },
            { name: "quantity", label: t("ecarts_m1.chiffrage.quantite"), type: "number", min: 0, step: "0.01", defaultValue: "1" },
            { name: "cout_unitaire", label: t("ecarts_m1.chiffrage.cout"), type: "number", min: 0 },
            { name: "unit_price", label: t("ecarts_m1.chiffrage.prix"), type: "number", min: 0 },
          ]}
        />
      </div>
      <label className="field">
        {t("ecarts_m1.chiffrage.offre")}
        <select value={offre} onChange={(e) => setOffre(e.target.value)} aria-label={t("ecarts_m1.chiffrage.choisirOffre")}>
          <option value="">—</option>
          {(offres.data ?? []).map((o) => (
            <option key={o.id} value={o.id}>
              {o.code} v{o.version} · {o.title}
            </option>
          ))}
        </select>
      </label>
      {s && (
        <>
          {s.taux_provisoires && <p className="muted">{t("ecarts_m1.provisoireNote")}</p>}
          {s.sous_marge_cible && <Badge tone="err">{t("ecarts_m1.chiffrage.sousMarge")}</Badge>}
          <DataTable
            rows={lignes}
            caption={t("ecarts_m1.chiffrage.title")}
            columns={[
              { key: "p", header: t("ecarts_m1.chiffrage.poste"), render: (l) => l.poste },
              { key: "m", header: t("commercial.col.montant"), num: true, render: (l) => montant(l.montant) },
            ]}
          />
          {s.par_lot.length > 0 && (
            <p className="muted">
              {t("ecarts_m1.chiffrage.nomenclature")} : {s.par_lot.map((l) => `${l.lot} ${montant(l.montant)}`).join(" · ")}
            </p>
          )}
        </>
      )}
      <h4>{t("ecarts_m1.derive.title", { seuil: derives.data?.seuil_pct ?? "" })}</h4>
      <DataTable
        rows={derives.data?.lignes ?? []}
        caption={t("ecarts_m1.derive.caption")}
        columns={[
          { key: "code", header: t("commercial.col.code"), render: (d) => `${d.code} · ${d.titre}` },
          { key: "av", header: t("ecarts_m1.derive.avancement"), num: true, render: (d) => `${formatNumber(d.avancement_pct)} %` },
          { key: "prevu", header: t("ecarts_m1.derive.prevu"), num: true, render: (d) => montant(d.cout_prevu_a_date) },
          { key: "reel", header: t("ecarts_m1.derive.reel"), num: true, render: (d) => montant(d.cout_reel) },
          {
            key: "derive",
            header: t("ecarts_m1.derive.derive"),
            render: (d) => <Badge tone={d.alerte ? "err" : "ok"}>{d.derive_pct === null ? "—" : `${d.derive_pct} %`}</Badge>,
          },
          {
            key: "act",
            header: "",
            render: (d) => (
              <ActionBar actions={[{ label: t("ecarts_m1.derive.besoins"), path: `/api/commercial/affaires/${d.id}/besoins-achat/`, tone: "ghost" }]} />
            ),
          },
        ]}
      />
    </SectionCard>
  );
}

function ProfilsContrats() {
  const { t } = useTranslation();
  const [contrat, setContrat] = useState("");
  const [jours, setJours] = useState("0");
  const [indice, setIndice] = useState("");
  const [base, setBase] = useState("");
  const contrats = useQuery({ queryKey: ["m1", "contrats"], queryFn: liste<ContratCourt>("/api/commercial/contracts/"), retry: 0 });
  const qs = `?jours_retard=${encodeURIComponent(jours || "0")}${indice && base ? `&indice=${encodeURIComponent(indice)}&indice_base=${encodeURIComponent(base)}` : ""}`;
  const calc = useQuery({
    queryKey: ["m1", "calculs", contrat, qs],
    queryFn: () => api.get<Calculs>(`/api/commercial/contracts/${contrat}/calculs/${qs}`),
    enabled: !!contrat,
    retry: 0,
  });
  const ret = useQuery({
    queryKey: ["m1", "retenues", contrat],
    queryFn: () => api.get<Retenues>(`/api/commercial/contracts/${contrat}/retenues/`),
    enabled: !!contrat,
    retry: 0,
  });
  const hab = useQuery({
    queryKey: ["m1", "habilitations", contrat],
    queryFn: () => api.get<Habilitations>(`/api/commercial/contracts/${contrat}/habilitations/`),
    enabled: !!contrat,
    retry: 0,
  });
  const c = calc.data;
  const choisi = (contrats.data ?? []).find((x) => x.id === contrat);
  return (
    <SectionCard title={t("ecarts_m1.contrats.title")}>
      <div className="action-bar-buttons">
        <QuickForm
          title={t("ecarts_m1.contrats.ajouterHabilitation")}
          endpoint="/api/commercial/habilitations-requises/"
          fields={[
            { name: "profile", label: t("ecarts_m1.contrats.profil"), type: "select", options: PROFILS.map((p) => ({ value: p, label: t(`ecarts_m1.profils.${p}`) })) },
            { name: "contract", label: t("ecarts_m1.contrats.contrat"), type: "select", options: (contrats.data ?? []).map((x) => ({ value: x.id, label: x.code })) },
            { name: "mot_cle", label: t("ecarts_m1.contrats.motCle"), required: true },
            { name: "libelle", label: t("ecarts_m1.contrats.libelle") },
          ]}
        />
      </div>
      <div className="action-bar-buttons">
        <label className="field">
          {t("ecarts_m1.contrats.contrat")}
          <select value={contrat} onChange={(e) => setContrat(e.target.value)} aria-label={t("ecarts_m1.contrats.choisir")}>
            <option value="">—</option>
            {(contrats.data ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.code} · {x.profile_label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {t("ecarts_m1.contrats.joursRetard")}
          <input type="number" min={0} value={jours} onChange={(e) => setJours(e.target.value)} />
        </label>
        <label className="field">
          {t("ecarts_m1.contrats.indice")}
          <input type="number" min={0} value={indice} onChange={(e) => setIndice(e.target.value)} />
        </label>
        <label className="field">
          {t("ecarts_m1.contrats.indiceBase")}
          <input type="number" min={0} value={base} onChange={(e) => setBase(e.target.value)} />
        </label>
      </div>
      {choisi && (choisi.status === "actif" || choisi.status === "suspendu") && (
        <ActionBar actions={[{ label: t("ecarts_m1.contrats.echeancier"), path: `/api/commercial/contracts/${choisi.id}/generer-echeancier/`, confirm: t("ecarts_m1.contrats.confirmEcheancier") }]} />
      )}
      {c && (
        <div data-testid="calculs-contrat">
          {c.provisoire && <p className="muted">{t("ecarts_m1.provisoireNote")}</p>}
          {c.alerte_duree && <p className="action-error">{c.alerte_duree}</p>}
          {c.controle_profil.map((m) => (
            <p key={m} className="action-error">
              {m}
            </p>
          ))}
          <DataTable
            caption={t("ecarts_m1.contrats.calculs")}
            rows={[
              { id: "ret", k: `${t("ecarts_m1.contrats.retenue")} (${c.taux_retenue_pct} %)`, v: montant(c.retenue_garantie) },
              { id: "net", k: t("ecarts_m1.contrats.net"), v: montant(c.net_apres_retenue) },
              { id: "pen", k: `${t("ecarts_m1.contrats.penalites")}${c.penalites_plafonnees ? ` (${t("ecarts_m1.contrats.plafond")})` : ""}`, v: montant(c.penalites) },
              { id: "idx", k: `${t("ecarts_m1.contrats.indexation")}${c.indexation ? ` (× ${c.indexation.coefficient})` : ""}`, v: c.indexation ? montant(c.indexation.montant_indexe) : "—" },
              { id: "duree", k: t("ecarts_m1.contrats.duree"), v: c.duree_mois === null ? "—" : `${c.duree_mois}` },
              { id: "rg", k: t("ecarts_m1.contrats.retenueCumulee"), v: montant(ret.data?.retenue_cumulee) },
              { id: "lib", k: t("ecarts_m1.contrats.liberation"), v: ret.data?.date_liberation ? formatDate(ret.data.date_liberation) : "—" },
            ]}
            columns={[
              { key: "k", header: t("ecarts_m1.chiffrage.poste"), render: (r) => r.k },
              { key: "v", header: t("ecarts_m1.contrats.valeur"), num: true, render: (r) => r.v },
            ]}
          />
        </div>
      )}
      {hab.data && (
        <>
          <h4>
            {t("ecarts_m1.contrats.habilitations")} : {hab.data.habilitations_requises.join(", ") || "—"}{" "}
            <Badge tone={hab.data.conforme ? "ok" : "err"}>{hab.data.conforme ? t("ecarts_m1.contrats.conforme") : t("ecarts_m1.contrats.nonConforme")}</Badge>
          </h4>
          <DataTable
            rows={hab.data.personnel.map((p) => ({ ...p, id: p.matricule }))}
            caption={t("ecarts_m1.contrats.habilitations")}
            columns={[
              { key: "m", header: t("ecarts_m1.contrats.matricule"), render: (p) => `${p.matricule} · ${p.nom}` },
              { key: "e", header: t("ecarts_m1.contrats.equipe"), render: (p) => p.equipe },
              { key: "x", header: t("ecarts_m1.contrats.manquantes"), render: (p) => p.manquantes.join(", ") || "—" },
            ]}
          />
        </>
      )}
    </SectionCard>
  );
}

function RaoRc() {
  const { t } = useTranslation();
  const raos = useQuery({ queryKey: ["m1", "rao"], queryFn: liste<Rao>("/api/commercial/tender-reviews/"), retry: 0 });
  const rcs = useQuery({ queryKey: ["m1", "rc"], queryFn: liste<Rc>("/api/commercial/revues-commande/"), retry: 0 });
  const criteres = useQuery({
    queryKey: ["m1", "criteres"],
    queryFn: () => api.get<{ criteres: { libelle: string; poids: number }[]; seuil_go: string; seuil_reserve: string }>("/api/commercial/tender-reviews/criteres-defaut/"),
    retry: 0,
  });
  const doc = (d: string | null) => (d ? <Badge tone="ok">{t("ecarts_m1.rao.archive")}</Badge> : <Badge tone="neutral">{t("ecarts_m1.rao.nonArchive")}</Badge>);
  return (
    <SectionCard title={t("ecarts_m1.rao.title")}>
      {criteres.data && (
        <p className="muted">
          {t("ecarts_m1.rao.criteres", { go: criteres.data.seuil_go, reserve: criteres.data.seuil_reserve })} :{" "}
          {criteres.data.criteres.map((c) => `${c.libelle} (${c.poids})`).join(" · ")}
        </p>
      )}
      <DataTable
        rows={raos.data ?? []}
        caption={t("ecarts_m1.rao.raos")}
        columns={[
          { key: "ref", header: t("ecarts_m1.rao.ref"), render: (r) => r.tender_ref || "—" },
          { key: "score", header: t("ecarts_m1.rao.note"), num: true, render: (r) => (r.score === null ? "—" : `${r.score} %`) },
          { key: "dec", header: t("ecarts_m1.rao.decision"), render: (r) => (r.decision_rao ? t(`ecarts_m1.rao.decisions.${r.decision_rao}`) : "—") },
          { key: "st", header: t("commercial.col.statut"), render: (r) => r.review_status_label },
          { key: "doc", header: t("ecarts_m1.rao.ged"), render: (r) => doc(r.document) },
          {
            key: "act",
            header: "",
            render: (r) => (r.document ? null : <ActionBar actions={[{ label: t("ecarts_m1.rao.archiver"), path: `/api/commercial/tender-reviews/${r.id}/archiver/`, tone: "ghost" }]} />),
          },
        ]}
      />
      <DataTable
        rows={rcs.data ?? []}
        caption={t("ecarts_m1.rao.rcs")}
        columns={[
          { key: "aff", header: t("commercial.col.affaire"), render: (r) => r.affaire_code },
          { key: "type", header: t("ecarts_m1.rao.typeRevue"), render: (r) => r.type_label },
          { key: "st", header: t("commercial.col.statut"), render: (r) => r.statut_label },
          { key: "doc", header: t("ecarts_m1.rao.ged"), render: (r) => doc(r.document) },
          {
            key: "act",
            header: "",
            render: (r) => (r.document ? null : <ActionBar actions={[{ label: t("ecarts_m1.rao.archiver"), path: `/api/commercial/revues-commande/${r.id}/archiver/`, tone: "ghost" }]} />),
          },
        ]}
      />
      <p className="muted">{t("ecarts_m1.rao.bs")}</p>
    </SectionCard>
  );
}

export function EcartsM1Section() {
  return (
    <>
      <AlertesEcheances />
      <Clients360 />
      <PipeProfilIndicateurs />
      <Chiffrage />
      <ProfilsContrats />
      <RaoRc />
      <ParametresM1 />
    </>
  );
}
