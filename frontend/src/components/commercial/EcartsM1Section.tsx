import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber, formatPercent } from "../../lib/format";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, Kpi, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";

/** Écarts M1 : paramètres provisoires, scoring 360°, alertes et échéances, pipe par profil, chiffrage et dérive,
 *  profils contractuels, habilitations, RAO / RC archivés, indicateurs commerciaux. */

interface Parametre {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  texte?: string;
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
  review_status?: string;
  review_status_label: string;
  document: string | null;
}
interface Rc {
  id: string;
  affaire_code: string;
  type_revue?: string;
  type_label: string;
  statut?: string;
  statut_label: string;
  document: string | null;
}

const NATURES = ["fourniture", "main_oeuvre", "sous_traitance", "equipement", "frais_directs"];
const PROFILS = ["marche_travaux", "maintenance"];
const montant = (v: string | null | undefined) => (v === null || v === undefined ? "••••••" : formatMoney(v));
const liste = <T,>(path: string) => () => api.listAll<T>(path);
/** Décimal API (« 12.50 ») au format français, décimales seulement si utiles. */
const dec = (v: string | number | null | undefined) => formatNumber(v, { decimals: Number.isInteger(Number(v)) ? 0 : 2 });
const taux = (v: string | number | null | undefined) => formatPercent(v, { decimals: Number.isInteger(Number(v)) ? 0 : 1 });
/** Valeur d'un champ de saisie sans zéros inutiles (« 5.00 » → « 5 », « 0.15 » inchangé) ; le point reste celui de l'API. */
const saisieBrute = (v: string) => (v.includes(".") ? v.replace(/\.?0+$/, "") : v);
/** Unités des paramètres (libellés serveur) → clés traduites ; « % », « 0/1 »… restent tels quels. */
const UNITE_CLE: Record<string, string> = { jours: "jours", mois: "mois", ans: "ans", pts: "pts", "‰ / jour": "permilleJour" };
/** Segment client : le serveur renvoie le libellé français (ou un code hérité) → code de traduction. */
const SEGMENT_CODE: Record<string, string> = {
  "Pétrole & Gaz": "petrole_gaz", petrole_gaz: "petrole_gaz", petrolier: "petrole_gaz",
  Industrie: "industrie", industrie: "industrie", "BTP / Construction": "construction", construction: "construction",
  Mines: "mines", mines: "mines", "Administration publique": "admin_pub", admin_pub: "admin_pub",
  Particulier: "particulier", particulier: "particulier", Autre: "autre", autre: "autre",
};
/** Étape d'opportunité (libellé serveur) → clé `pipeline.*`. */
const ETAPE_CODE: Record<string, string> = {
  Prospection: "prospection", Qualification: "qualification", "Offre soumise": "offre", Offre: "offre",
  "Négociation": "negociation", "Gagnée": "gagne", Perdue: "perdu",
};
/** Premier nombre d'un libellé serveur (« … depuis 90 jours » → 90). */
const nombreDans = (s: string) => Number(/\d+/.exec(s)?.[0] ?? 0);

function ParametresM1() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const params = useQuery({ queryKey: ["m1", "parametres"], queryFn: liste<Parametre>("/api/commercial/parametres/"), retry: 0 });
  const [saisie, setSaisie] = useState<Record<string, string>>({});
  const [saisieTexte, setSaisieTexte] = useState<Record<string, string>>({});
  const [erreur, setErreur] = useState<string | null>(null);
  const done = () => {
    setErreur(null);
    void qc.invalidateQueries({ queryKey: ["m1"] });
  };
  const enregistrer = useMutation({
    mutationFn: (v: { id: string; valeur?: string; texte?: string }) =>
      api.patch(`/api/commercial/parametres/${v.id}/`, v.texte !== undefined ? { texte: v.texte, ...(v.valeur !== undefined ? { valeur: v.valeur } : {}) } : { valeur: v.valeur }),
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
  const unite = (u: string) => (UNITE_CLE[u] ? t(`revueR2.pipeline.unites.${UNITE_CLE[u]}`) : u);
  const modifie = (p: Parametre) => (saisie[p.id] !== undefined && saisie[p.id] !== p.valeur) || (saisieTexte[p.id] !== undefined && saisieTexte[p.id] !== p.texte);
  const cols: Column<Parametre>[] = [
    { key: "libelle", header: t("ecarts_m1.params.libelle"), render: (p) => p.label, sortValue: (p) => p.label },
    {
      key: "valeur",
      header: t("ecarts_m1.params.valeur"),
      width: 340,
      render: (p) => {
        const texte = saisieTexte[p.id] ?? p.texte ?? "";
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            {p.unite !== "texte" && (
              <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input
                  className="control"
                  inputMode="decimal"
                  style={{ width: "7rem", textAlign: "right", fontVariantNumeric: "tabular-nums" }}
                  aria-label={p.label}
                  value={saisie[p.id] ?? saisieBrute(p.valeur)}
                  onChange={(e) => setSaisie({ ...saisie, [p.id]: e.target.value })}
                />
                <span className="muted">{unite(p.unite)}</span>
              </span>
            )}
            {p.texte !== undefined && p.texte !== "" && (
              <textarea
                className="control"
                // Hauteur ajustée au texte : la définition reste lisible sans défilement interne.
                rows={Math.min(8, Math.max(1, Math.ceil(texte.length / 42)))}
                style={{ width: "100%", resize: "vertical" }}
                aria-label={`${p.label} — ${t("ecarts_suivi.texte")}`}
                value={texte}
                onChange={(e) => setSaisieTexte({ ...saisieTexte, [p.id]: e.target.value })}
              />
            )}
          </div>
        );
      },
    },
    {
      key: "statut",
      header: t("ecarts_m1.params.statut"),
      render: (p) => <Badge tone={p.est_provisoire ? "warn" : "ok"}>{t(`ecarts_m1.params.${p.statut_valeur}`)}</Badge>,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (p) => (
        <div className="action-bar-buttons" style={{ flexWrap: "nowrap", justifyContent: "flex-end" }}>
          {modifie(p) && (
            <button
              type="button"
              className="btn primary sm"
              onClick={() =>
                enregistrer.mutate({
                  id: p.id,
                  ...(saisie[p.id] !== undefined && saisie[p.id] !== p.valeur ? { valeur: saisie[p.id] } : {}),
                  ...(saisieTexte[p.id] !== undefined && saisieTexte[p.id] !== p.texte ? { texte: saisieTexte[p.id] } : {}),
                })
              }
            >
              {t("ecarts_m1.params.enregistrer")}
            </button>
          )}
          {p.est_provisoire && (
            <button type="button" className="btn ghost sm" onClick={() => confirmer.mutate(p.id)}>
              {t("ecarts_m1.params.confirmer")}
            </button>
          )}
        </div>
      ),
    },
  ];
  return (
    <SectionCard title={t("ecarts_m1.params.title")}>
      {provisoires > 0 && (
        <div className="banner warn" role="note" data-testid="alerte-provisoire-m1">
          <SlidersHorizontal size={18} aria-hidden />
          <div className="banner-body">
            <span className="banner-title">{t("ecarts_m1.params.warn", { count: provisoires })}</span>
          </div>
        </div>
      )}
      {erreur && (
        <p className="action-error" role="alert">
          {erreur}
        </p>
      )}
      <div data-testid="parametres-m1">
        <DataTable rows={lignes} columns={cols} caption={t("ecarts_m1.params.title")} density="compact" />
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
    { key: "client", header: t("ecarts_m1.clients.client"), render: (c) => c.client, sortValue: (c) => c.client },
    {
      key: "segment",
      header: t("ecarts_m1.clients.segment"),
      render: (c) => (SEGMENT_CODE[c.segment] ? t(`revueR2.pipeline.segments.${SEGMENT_CODE[c.segment]}`) : c.segment || "—"),
    },
    {
      key: "score",
      header: t("ecarts_m1.clients.score"),
      num: true,
      sortValue: (c) => c.score_calcule,
      // Score calculé en valeur principale ; le score enregistré (fiche client) en ligne secondaire.
      render: (c) => (
        <>
          {c.score_calcule}
          <span className="cell-sub">{t("revueR2.pipeline.scoreEnregistre", { n: c.score_enregistre })}</span>
        </>
      ),
    },
    { key: "contact", header: t("ecarts_m1.clients.dernierContact"), render: (c) => formatDate(c.dernier_contact), sortValue: (c) => c.dernier_contact },
    {
      key: "signaux",
      header: t("ecarts_m1.clients.signaux"),
      render: (c) =>
        c.signaux.length ? (
          <span className="action-bar-buttons">
            {c.signaux.map((s) => (
              <Badge key={s.code} tone="warn">
                {t(`revueR2.pipeline.signaux.${s.code}`, { n: nombreDans(s.libelle), defaultValue: s.libelle })}
              </Badge>
            ))}
          </span>
        ) : (
          <Badge tone="ok">{t("ecarts_m1.clients.ras")}</Badge>
        ),
    },
  ];
  const lignes = signaux.data?.lignes ?? [];
  return (
    <SectionCard
      title={t("ecarts_m1.clients.title")}
      actions={<ActionBar actions={[{ label: t("ecarts_m1.clients.recalculer"), path: "/api/commercial/profiles/recalculer-scores/", tone: "ghost" }]} />}
    >
      {signaux.data?.provisoire && <p className="muted">{t("ecarts_m1.provisoireNote")}</p>}
      <DataTable rows={lignes} columns={cols} caption={t("ecarts_m1.clients.title")} />
      <label className="field" style={{ marginTop: "var(--space-4)", maxWidth: 420 }}>
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
              { key: "p", header: t("ecarts_m1.clients.poids"), num: true, render: (c) => dec(c.poids) },
              { key: "n", header: t("ecarts_m1.clients.note"), num: true, render: (c) => dec(c.note) },
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
  /** Motif serveur (français) → libellé traduit ; repli sur le texte reçu. */
  const motif = (m: string) =>
    m.startsWith("Sans mouvement")
      ? t("revueR2.pipeline.motifs.sansMouvement", { n: nombreDans(m) })
      : m.startsWith("Date de clôture")
        ? t("revueR2.pipeline.motifs.clotureDepassee")
        : m;
  /** Palier d'échéance (« depassee », « j15 ») → « Dépassée », « J-15 ». */
  const palier = (p: string | null) =>
    !p ? "—" : p === "depassee" ? t("revueR2.pipeline.palierDepasse") : /^j\d+$/.test(p) ? t("revueR2.pipeline.palierJ", { n: p.slice(1) }) : p;
  return (
    <SectionCard
      title={t("ecarts_m1.alertes.title")}
      actions={<ActionBar actions={[{ label: t("ecarts_m1.alertes.relancer"), path: "/api/commercial/pilotage/relancer/", tone: "ghost" }]} />}
    >
      <h4>{t("ecarts_m1.alertes.opportunites", { jours: opp.data ? dec(opp.data.jours) : "" })}</h4>
      <DataTable
        rows={opp.data?.lignes ?? []}
        caption={t("ecarts_m1.alertes.opportunites", { jours: opp.data ? dec(opp.data.jours) : "" })}
        columns={[
          { key: "code", header: t("commercial.col.code"), render: (o) => <span className="cell-nowrap">{o.code}</span>, sortValue: (o) => o.code },
          { key: "objet", header: t("commercial.col.titre"), render: (o) => o.objet },
          { key: "etape", header: t("ecarts_m1.alertes.etape"), render: (o) => (ETAPE_CODE[o.etape] ? t(`pipeline.${ETAPE_CODE[o.etape]}`) : o.etape) },
          { key: "client", header: t("commercial.col.client"), render: (o) => o.client ?? "—" },
          { key: "motifs", header: t("ecarts_m1.alertes.motifs"), render: (o) => o.motifs.map(motif).join(" · ") },
        ]}
      />
      <h4>{t("ecarts_m1.alertes.echeances", { paliers: (ech.data?.paliers ?? []).filter((p) => p > 0).map((p) => t("revueR2.pipeline.palierJ", { n: p })).join(" / ") })}</h4>
      {ech.data?.provisoire && <p className="muted">{t("ecarts_m1.provisoireNote")}</p>}
      <DataTable
        rows={(ech.data?.lignes ?? []).map((e) => ({ ...e, id: `${e.type}-${e.id}` }))}
        caption={t("ecarts_m1.alertes.echeancesCaption")}
        columns={[
          { key: "type", header: t("ecarts_m1.alertes.type"), render: (e) => t(`ecarts_m1.alertes.types.${e.type}`) },
          { key: "code", header: t("commercial.col.code"), render: (e) => <span className="cell-nowrap">{e.code}</span> },
          { key: "lib", header: t("ecarts_m1.alertes.objet"), render: (e) => e.libelle },
          { key: "date", header: t("ecarts_m1.alertes.date"), render: (e) => <span className="cell-nowrap">{formatDate(e.date_echeance)}</span>, sortValue: (e) => e.date_echeance },
          {
            key: "palier",
            header: t("ecarts_m1.alertes.palier"),
            sortValue: (e) => e.jours,
            // Rouge réservé au dépassement ; un palier à venir reste un avertissement.
            render: (e) => <Badge tone={e.jours < 0 ? "err" : e.jours <= 30 ? "warn" : "neutral"}>{palier(e.palier)}</Badge>,
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
          <Kpi label={t("ecarts_m1.indic.transformation")} value={taux(i.taux_transformation_pct)} tone="accent" />
          <Kpi label={t("ecarts_m1.indic.scoreMoyen")} value={i.score_moyen === null ? "—" : formatNumber(i.score_moyen, { decimals: 1 })} tone="ok" />
          <Kpi label={t("ecarts_m1.indic.sousSeuil")} value={i.clients_sous_seuil} tone="warn" />
        </div>
      )}
      <DataTable
        rows={(profils.data?.lignes ?? []).map((l) => ({ ...l, id: l.profil }))}
        caption={t("ecarts_m1.profil.title")}
        columns={[
          { key: "p", header: t("ecarts_m1.profil.profil"), render: (l) => t(`revueR2.pipeline.profils.${l.profil || "nonRenseigne"}`, { defaultValue: l.libelle }) },
          { key: "n", header: t("ecarts_m1.profil.nombre"), num: true, render: (l) => formatNumber(l.nombre), sortValue: (l) => l.nombre },
          { key: "m", header: t("ecarts_m1.profil.montant"), num: true, render: (l) => montant(l.montant), sortValue: (l) => Number(l.montant ?? 0) },
          { key: "pp", header: t("ecarts_m1.profil.pondere"), num: true, render: (l) => montant(l.pondere) },
          { key: "g", header: t("ecarts_m1.profil.gagneesPerdues"), num: true, render: (l) => `${l.gagnees} / ${l.perdues}` },
          { key: "c", header: t("ecarts_m1.profil.conversion"), num: true, render: (l) => taux(l.conversion_pct) },
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
        { id: "fi", poste: `${t("ecarts_m1.chiffrage.fi")} (${taux(s.taux.frais_indirects)})`, montant: s.frais_indirects },
        { id: "al", poste: `${t("ecarts_m1.chiffrage.aleas")} (${taux(s.taux.aleas)})`, montant: s.aleas },
        { id: "pr", poste: t("ecarts_m1.chiffrage.pr"), montant: s.prix_revient },
        { id: "pv", poste: `${t("ecarts_m1.chiffrage.pv")} (${taux(s.taux.marge)})`, montant: s.prix_vente_cible },
        { id: "po", poste: t("ecarts_m1.chiffrage.prixOffre"), montant: s.prix_offre },
        { id: "mo", poste: `${t("ecarts_m1.chiffrage.margeOffre")} (${taux(s.taux_marge_offre_pct)})`, montant: s.marge_offre },
      ]
    : [];
  return (
    <SectionCard
      title={t("ecarts_m1.chiffrage.title")}
      actions={
        <SectionActions>
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
        </SectionActions>
      }
    >
      <label className="field" style={{ maxWidth: 520 }}>
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
      <h4>{t("ecarts_m1.derive.title", { seuil: derives.data ? dec(derives.data.seuil_pct) : "" })}</h4>
      <DataTable
        rows={derives.data?.lignes ?? []}
        caption={t("ecarts_m1.derive.caption")}
        columns={[
          {
            key: "code",
            header: t("commercial.col.code"),
            sortValue: (d) => d.code,
            render: (d) => (
              <>
                <span className="cell-nowrap">{d.code}</span> · {d.titre}
              </>
            ),
          },
          { key: "av", header: t("ecarts_m1.derive.avancement"), num: true, render: (d) => formatPercent(d.avancement_pct) },
          { key: "prevu", header: t("ecarts_m1.derive.prevu"), num: true, render: (d) => montant(d.cout_prevu_a_date) },
          { key: "reel", header: t("ecarts_m1.derive.reel"), num: true, render: (d) => montant(d.cout_reel) },
          {
            key: "derive",
            header: t("ecarts_m1.derive.derive"),
            sortValue: (d) => (d.derive_pct === null ? null : Number(d.derive_pct)),
            render: (d) => <Badge tone={d.alerte ? "err" : "ok"}>{taux(d.derive_pct)}</Badge>,
          },
          actionsColumn<Derive>(t("ui.actions"), (d) => [{ label: t("ecarts_m1.derive.besoins"), path: `/api/commercial/affaires/${d.id}/besoins-achat/`, tone: "ghost" }]),
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
    <SectionCard
      title={t("ecarts_m1.contrats.title")}
      actions={
        <SectionActions>
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
        </SectionActions>
      }
    >
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0 var(--space-4)", alignItems: "end" }}>
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
              { id: "ret", k: `${t("ecarts_m1.contrats.retenue")} (${taux(c.taux_retenue_pct)})`, v: montant(c.retenue_garantie) },
              { id: "net", k: t("ecarts_m1.contrats.net"), v: montant(c.net_apres_retenue) },
              { id: "pen", k: `${t("ecarts_m1.contrats.penalites")}${c.penalites_plafonnees ? ` (${t("ecarts_m1.contrats.plafond")})` : ""}`, v: montant(c.penalites) },
              { id: "idx", k: `${t("ecarts_m1.contrats.indexation")}${c.indexation ? ` (× ${dec(c.indexation.coefficient)})` : ""}`, v: c.indexation ? montant(c.indexation.montant_indexe) : "—" },
              { id: "duree", k: t("ecarts_m1.contrats.duree"), v: c.duree_mois === null ? "—" : `${c.duree_mois}` },
              { id: "rg", k: t("ecarts_m1.contrats.retenueCumulee"), v: montant(ret.data?.retenue_cumulee) },
              { id: "lib", k: t("ecarts_m1.contrats.liberation"), v: formatDate(ret.data?.date_liberation) },
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
          {t("ecarts_m1.rao.criteres", { go: dec(criteres.data.seuil_go), reserve: dec(criteres.data.seuil_reserve) })} :{" "}
          {criteres.data.criteres.map((c) => `${c.libelle} (${dec(c.poids)})`).join(" · ")}
        </p>
      )}
      <h4>{t("ecarts_m1.rao.raos")}</h4>
      <DataTable
        rows={raos.data ?? []}
        caption={t("ecarts_m1.rao.raos")}
        columns={[
          { key: "ref", header: t("ecarts_m1.rao.ref"), render: (r) => r.tender_ref || "—" },
          { key: "score", header: t("ecarts_m1.rao.note"), num: true, render: (r) => taux(r.score), sortValue: (r) => (r.score === null ? null : Number(r.score)) },
          { key: "dec", header: t("ecarts_m1.rao.decision"), render: (r) => (r.decision_rao ? t(`ecarts_m1.rao.decisions.${r.decision_rao}`) : "—") },
          {
            key: "st",
            header: t("commercial.col.statut"),
            render: (r) => (r.review_status ? t(`revueR2.pipeline.statutsRao.${r.review_status}`, { defaultValue: r.review_status_label }) : r.review_status_label),
          },
          { key: "doc", header: t("ecarts_m1.rao.ged"), render: (r) => doc(r.document) },
          actionsColumn<Rao>(t("ui.actions"), (r) => (r.document ? [] : [{ label: t("ecarts_m1.rao.archiver"), path: `/api/commercial/tender-reviews/${r.id}/archiver/`, tone: "ghost" }])),
        ]}
      />
      <h4>{t("ecarts_m1.rao.rcs")}</h4>
      <DataTable
        rows={rcs.data ?? []}
        caption={t("ecarts_m1.rao.rcs")}
        columns={[
          { key: "aff", header: t("commercial.col.affaire"), render: (r) => <span className="cell-nowrap">{r.affaire_code}</span> },
          {
            key: "type",
            header: t("ecarts_m1.rao.typeRevue"),
            render: (r) => (r.type_revue ? t(`revueR2.pipeline.typesRc.${r.type_revue}`, { defaultValue: r.type_label }) : r.type_label),
          },
          {
            key: "st",
            header: t("commercial.col.statut"),
            render: (r) => (r.statut ? t(`revueR2.pipeline.statutsRc.${r.statut}`, { defaultValue: r.statut_label }) : r.statut_label),
          },
          { key: "doc", header: t("ecarts_m1.rao.ged"), render: (r) => doc(r.document) },
          actionsColumn<Rc>(t("ui.actions"), (r) => (r.document ? [] : [{ label: t("ecarts_m1.rao.archiver"), path: `/api/commercial/revues-commande/${r.id}/archiver/`, tone: "ghost" }])),
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
