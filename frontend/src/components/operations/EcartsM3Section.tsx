import { useQuery } from "@tanstack/react-query";
import { FileDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, Kpi, Menu, QuickForm, SectionCard } from "../ui";
import type { ActionDef, Column } from "../ui";
import { CardActions } from "../ui/Board";
import { actionsColumn } from "../ui/DataTable";
import { decimales, statutLabel, useClientPage } from "./outils";

interface Parametre {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  est_provisoire: boolean;
  confirme_par_nom: string | null;
}
interface Of {
  id: string;
  code: string;
  label: string;
  status: string;
  status_label: string;
  scope: string;
  planned_start: string | null;
  planned_end: string | null;
  motif_replanification: string;
}
interface Besoin {
  id: string;
  ordre_code: string;
  article_code: string;
  article_label: string;
  quantite: string;
  statut: string;
  statut_label: string;
  disponible: string | null;
  demande_achat_code: string | null;
}
interface Fiche {
  id: string;
  code: string;
  ordre_code: string;
  outillage: string;
  statut: string;
  statut_label: string;
  valide_par_nom: string | null;
}
interface Rapport {
  id: string;
  code: string;
  ordre_code: string;
  type_label: string;
  date: string;
  quantite_realisee: string;
  quantite_rebut: string;
  avancement: number | null;
  statut: string;
  statut_label: string;
}
interface FicheControle {
  id: string;
  code: string;
  ordre_code: string;
  date: string;
  objet: string;
  conforme: boolean;
  controle_par_nom: string | null;
}
interface Transfert {
  id: string;
  code: string;
  type_label: string;
  ordre_code: string;
  destination: string;
  lignes: { designation: string; quantite: string }[];
  statut: string;
  statut_label: string;
  reserves: string;
}
interface AttachementRow {
  id: string;
  code: string;
  ordre_code: string;
  situation_code: string | null;
  date: string;
  designation: string;
  unite: string;
  quantite: string;
  montant: string | null;
  statut: string;
  statut_label: string;
  signataire_client: string;
}
interface Situation {
  id: string;
  code: string;
  label: string;
  status: string;
  status_label: string;
  amount: string | null;
  montant_attachements: string | null;
  recue_le: string | null;
  recue_signataire: string;
}
interface Pointage {
  id: string;
  code: string;
  ordre_code: string;
  worker_name_filled: string | null;
  date: string;
  hours: string;
  hours_type?: string;
  hours_type_label: string;
  nature_mo?: string;
  nature_mo_label: string;
  status: string;
  status_label: string;
}
interface AffaireSuivi {
  affaire: string;
  affaire_code: string;
  affaire_label: string;
  avancement_pct: string | null;
  chiffre_affaires: string | null;
  couts_engages: string | null;
  cout_a_terminaison: string | null;
  marge_a_terminaison: string | null;
  marge_pct: string | null;
}
interface OfSuivi {
  ordre: string;
  code: string;
  label: string;
  affaire: string | null;
  avancement_pct: string | null;
}
interface Suivi {
  methode: number;
  ordres: OfSuivi[];
  affaires: AffaireSuivi[];
}
interface Indicateurs {
  productivite_pct: string | null;
  taux_rebut_pct: string | null;
  heures_directes: string;
  heures_indirectes: string;
  of_en_retard: number;
  ruptures_ouvertes: number;
}
interface ChargeJour {
  date: string;
  scope: string;
  resource: string;
  planned_hours: string;
  capacity: string | null;
  overload: boolean;
}
interface Escalade {
  id: string;
  scope: string;
  resource: string;
  semaine: string;
  surcharge_pct: string;
}
interface Registre {
  id: string;
  titre: string;
  reference: string;
  type: string | null;
  objet: string;
  lie_le: string;
}
interface Dossier {
  id: string;
  ordre_code: string;
  sha256: string;
  retention_years: number;
  created_at: string;
}
interface Option {
  id: string;
  code: string;
  label?: string;
  title?: string;
  nom_complet?: string;
}

const fcfa = (v: string | null) => formatMoney(v);
const pct = (v: string | null) => (v === null ? "—" : `${formatNumber(Number(v))} %`);
const q = <T,>(key: string, path: string) => ({ queryKey: ["ecarts-m3", key], queryFn: () => api.listAll<T>(path), retry: 0 });

type AffaireLigne = AffaireSuivi & { id: string };
type ChargeLigne = ChargeJour & { id: string };

const qte = (v: string) => formatNumber(Number(v), { decimals: decimales(v) });
const nombre = (v: string | null) => (v === null ? null : Number(v));
const telecharger = (path: string, name: string) => void api.download(path, name).catch(() => undefined);
/** Colonne d'actions qui ne passe pas à la ligne (boutons « Valoriser par les attachements », « Transférer en paie »…). */
const sansRetour = <T,>(col: Column<T>): Column<T> => ({ ...col, render: (row) => <span className="cell-nowrap">{col.render(row)}</span> });
/** Rapport d'exécution archivé : titre et type rendus dans la langue de l'interface (l'archive GED reste en français). */
const RAPPORT_EXEC = /^Rapport d'exécution\s+(\S+)$/;
/** Unités de paramètres traduites ; « 0 / 1 » (booléen) et « code » sont rendus à part. */
const UNITES_TRADUITES = new Set(["jours", "semaines", "ans"]);
/** Type de document du registre sans code de module (« Rapports d'exécution (M3) » → « Rapports d'exécution »). */
const sansModule = (v: string) => v.replace(/\s*\(M\d+[a-z]?\)\s*$/i, "");

/** Actions d'une ligne : action principale + menu (CardActions), puis export PDF du document. */
function LigneActions({ actions, pdf }: { actions: ActionDef[]; pdf: { path: string; name: string } }) {
  const { t } = useTranslation();
  return (
    <div className="action-bar-buttons" style={{ justifyContent: "flex-end", flexWrap: "nowrap", alignItems: "center", whiteSpace: "nowrap" }}>
      {actions.length > 0 && <CardActions actions={actions} align="end" />}
      <button type="button" className="btn ghost sm" onClick={() => telecharger(pdf.path, pdf.name)} aria-label={t("tableaux.operations.pdfDe", { nom: pdf.name.replace(/\.pdf$/, "") })}>
        <FileDown size={14} aria-hidden="true" /> {t("ecarts_m3.pdf")}
      </button>
    </div>
  );
}

/** Écarts M3 (lot 2) : paramètres provisoires, préparation, rapports, transferts, attachements, suivi, reporting, registre. */
export function EcartsM3Section() {
  const { t } = useTranslation();
  const k = (s: string) => t(`ecarts_m3.${s}`);
  const parametres = useQuery(q<Parametre>("parametres", "/api/operations/parametres/")).data ?? [];
  const ordres = useQuery(q<Of>("ordres", "/api/operations/ordres/")).data ?? [];
  const besoins = useQuery(q<Besoin>("besoins", "/api/operations/besoins-matiere/")).data ?? [];
  const fiches = useQuery(q<Fiche>("fiches", "/api/operations/fiches-preparation/")).data ?? [];
  const rapports = useQuery(q<Rapport>("rapports", "/api/operations/rapports/")).data ?? [];
  const controles = useQuery(q<FicheControle>("controles", "/api/operations/fiches-controle/")).data ?? [];
  const transferts = useQuery(q<Transfert>("transferts", "/api/operations/transferts/")).data ?? [];
  const attachements = useQuery(q<AttachementRow>("attachements", "/api/operations/attachements/")).data ?? [];
  const situations = useQuery(q<Situation>("situations", "/api/operations/situations/")).data ?? [];
  const pointages = useQuery(q<Pointage>("pointages", "/api/operations/pointages/?page_size=100")).data ?? [];
  const escalades = useQuery(q<Escalade>("escalades", "/api/operations/escalades/")).data ?? [];
  const dossiers = useQuery(q<Dossier>("dossiers", "/api/operations/dossiers/")).data ?? [];
  const articles = useQuery(q<Option>("articles", "/api/referentiels/articles/")).data ?? [];
  const affaires = useQuery(q<Option>("affaires", "/api/commercial/affaires/")).data ?? [];
  const employes = useQuery(q<Option>("employes", "/api/rh-paie/employes/")).data ?? [];
  const suivi = useQuery({ queryKey: ["ecarts-m3", "suivi"], queryFn: () => api.get<Suivi>("/api/operations/ordres/suivi/"), retry: 0 }).data;
  const ind = useQuery({ queryKey: ["ecarts-m3", "indicateurs"], queryFn: () => api.get<Indicateurs>("/api/operations/ordres/indicateurs/"), retry: 0 }).data;
  const charge = useQuery({
    queryKey: ["ecarts-m3", "charge-jour"],
    queryFn: () => api.get<{ lignes: ChargeJour[] }>("/api/operations/ordres/charge-journaliere/?jours=14"),
    retry: 0,
  }).data;
  const registre = useQuery({ queryKey: ["ecarts-m3", "registre"], queryFn: () => api.get<Registre[]>("/api/operations/dossiers/registre/"), retry: 0 }).data ?? [];

  const ofOpts = ordres.filter((o) => o.status !== "annule").map((o) => ({ value: o.id, label: `${o.code} — ${o.label}` }));
  const ofActifs = ofOpts.filter((o) => !ordres.find((x) => x.id === o.value && x.status === "cloture"));
  const articleOpts = articles.map((a) => ({ value: a.id, label: `${a.code} — ${a.label ?? ""}` }));
  const affaireOpts = affaires.map((a) => ({ value: a.id, label: `${a.code} — ${a.title ?? ""}` }));
  const employeOpts = employes.map((e) => ({ value: e.id, label: `${e.code} — ${e.nom_complet ?? ""}` }));
  const situationOpts = situations
    .filter((s) => s.status === "brouillon" || s.status === "soumise")
    .map((s) => ({ value: s.id, label: `${s.code} — ${s.label}` }));
  const provisoires = parametres.filter((p) => p.est_provisoire).length;
  const lignesSurcharge = (charge?.lignes ?? []).filter((l) => Number(l.planned_hours) > 0);

  const actionsHeader = t("ui.actions");
  const perimetre = (scope: string) => (scope === "atelier" || scope === "chantier" ? t(`tableaux.operations.scope.${scope}`) : scope);

  // Tableaux longs (dizaines de situations, centaines de pointages) : pagination client par 20.
  const pageSituations = useClientPage(situations);
  const pagePointages = useClientPage(pointages);
  const pageOrdres = useClientPage(ordres);
  const pageCharge = useClientPage(lignesSurcharge.map((l) => ({ ...l, id: `${l.date}-${l.scope}-${l.resource}` })));

  const colsParametres: Column<Parametre>[] = [
    {
      key: "libelle",
      header: k("parametres.libelle"),
      sortValue: (p) => p.label,
      render: (p) => <span title={p.code}>{t(`revueR2.operations.parametres.${p.code}`, { defaultValue: p.label })}</span>,
    },
    {
      key: "valeur",
      header: k("parametres.valeur"),
      num: true,
      render: (p) => {
        const n = Number(p.valeur);
        if (p.unite.replace(/\s/g, "") === "0/1") return n ? t("revueR2.operations.oui") : t("revueR2.operations.non");
        const valeur = formatNumber(n, { decimals: decimales(p.valeur) });
        if (p.unite === "code" || !p.unite) return valeur;
        const unite = UNITES_TRADUITES.has(p.unite) ? t(`revueR2.operations.unites.${p.unite}`) : p.unite;
        return <span className="cell-nowrap">{`${valeur} ${unite}`}</span>;
      },
    },
    {
      key: "statut",
      header: k("parametres.statut"),
      sortValue: (p) => p.est_provisoire,
      render: (p) => (p.est_provisoire ? <Badge tone="warn">{t("tableaux.operations.provisoire")}</Badge> : <Badge tone="ok">{k("confirme")}</Badge>),
    },
    actionsColumn<Parametre>(
      actionsHeader,
      (p) => [
        { label: k("parametres.modifier"), path: `/api/operations/parametres/${p.id}/modifier/`, prompt: { name: "valeur", label: k("parametres.valeur") } },
        ...(p.est_provisoire ? [{ label: k("parametres.confirmer"), path: `/api/operations/parametres/${p.id}/confirmer/`, confirm: k("parametres.confirmerQ") }] : []),
      ],
      (p) => (p.est_provisoire ? k("parametres.confirmer") : undefined),
    ),
  ];
  const colsFiches: Column<Fiche>[] = [
    { key: "code", header: k("code"), sortValue: (f) => f.code, render: (f) => f.code },
    { key: "of", header: k("of"), sortValue: (f) => f.ordre_code, render: (f) => f.ordre_code },
    { key: "outillage", header: k("preparation.outillage"), render: (f) => f.outillage || "—" },
    {
      key: "statut",
      header: k("statut"),
      sortValue: (f) => f.statut_label,
      render: (f) => (
        <>
          <Badge tone={f.statut === "validee" ? "ok" : "warn"}>{statutLabel("fiche", f.statut, f.statut_label)}</Badge> {f.valide_par_nom ?? ""}
        </>
      ),
    },
    {
      key: "__actions",
      header: <span className="sr-only">{actionsHeader}</span>,
      render: (f) => (
        <LigneActions
          actions={f.statut === "brouillon" ? [{ label: k("preparation.valider"), path: `/api/operations/fiches-preparation/${f.id}/valider/` }] : []}
          pdf={{ path: `/api/operations/fiches-preparation/${f.id}/?export=pdf`, name: `${f.code}.pdf` }}
        />
      ),
    },
  ];
  const colsBesoins: Column<Besoin>[] = [
    { key: "of", header: k("of"), sortValue: (b) => b.ordre_code, render: (b) => b.ordre_code },
    { key: "article", header: k("preparation.article"), sortValue: (b) => b.article_code, render: (b) => `${b.article_code} · ${b.article_label}` },
    { key: "quantite", header: k("preparation.quantite"), num: true, sortValue: (b) => Number(b.quantite), render: (b) => qte(b.quantite) },
    { key: "disponible", header: k("preparation.disponible"), num: true, render: (b) => (b.disponible === null ? "—" : qte(b.disponible)) },
    {
      key: "statut",
      header: k("statut"),
      sortValue: (b) => b.statut_label,
      render: (b) => <Badge tone={b.statut === "rupture" ? "err" : b.statut === "reserve" || b.statut === "servi" ? "ok" : "warn"}>{statutLabel("besoin", b.statut, b.statut_label)}</Badge>,
    },
    { key: "da", header: k("preparation.da"), render: (b) => b.demande_achat_code ?? "—" },
  ];
  const colsRapports: Column<Rapport>[] = [
    { key: "code", header: k("code"), sortValue: (r) => r.code, render: (r) => r.code },
    { key: "of", header: k("of"), sortValue: (r) => r.ordre_code, render: (r) => r.ordre_code },
    { key: "type", header: k("rapports.type"), render: (r) => r.type_label },
    { key: "date", header: k("date"), sortValue: (r) => r.date, render: (r) => formatDate(r.date) },
    { key: "realise", header: k("rapports.realise"), num: true, render: (r) => qte(r.quantite_realisee) },
    { key: "rebut", header: k("rapports.rebut"), num: true, render: (r) => qte(r.quantite_rebut) },
    { key: "pct", header: k("rapports.pct"), num: true, sortValue: (r) => r.avancement, render: (r) => (r.avancement === null ? "—" : `${formatNumber(r.avancement)} %`) },
    { key: "statut", header: k("statut"), sortValue: (r) => r.statut_label, render: (r) => <Badge tone={r.statut === "valide" ? "ok" : "warn"}>{statutLabel("rapport", r.statut, r.statut_label)}</Badge> },
    {
      key: "__actions",
      header: <span className="sr-only">{actionsHeader}</span>,
      render: (r) => (
        <LigneActions
          actions={r.statut === "brouillon" ? [{ label: k("rapports.valider"), path: `/api/operations/rapports/${r.id}/valider/` }] : []}
          pdf={{ path: `/api/operations/rapports/${r.id}/?export=pdf`, name: `${r.code}.pdf` }}
        />
      ),
    },
  ];
  const colsControles: Column<FicheControle>[] = [
    { key: "code", header: k("code"), sortValue: (c) => c.code, render: (c) => c.code },
    { key: "of", header: k("of"), sortValue: (c) => c.ordre_code, render: (c) => c.ordre_code },
    { key: "date", header: k("date"), sortValue: (c) => c.date, render: (c) => formatDate(c.date) },
    { key: "objet", header: k("controle.objet"), render: (c) => c.objet },
    {
      key: "resultat",
      header: k("controle.resultat"),
      sortValue: (c) => c.conforme,
      render: (c) => (
        <>
          <Badge tone={c.conforme ? "ok" : "err"}>{c.conforme ? k("controle.conforme") : k("controle.nonConforme")}</Badge> {c.controle_par_nom ?? ""}
        </>
      ),
    },
  ];
  const colsTransferts: Column<Transfert>[] = [
    {
      key: "code",
      header: k("code"),
      sortValue: (b) => b.code,
      render: (b) => (
        <>
          {b.code} <span className="muted">{b.type_label}</span>
        </>
      ),
    },
    { key: "of", header: k("of"), sortValue: (b) => b.ordre_code, render: (b) => b.ordre_code },
    { key: "destination", header: k("transferts.destination"), render: (b) => b.destination },
    { key: "lignes", header: t("tableaux.operations.contenu"), render: (b) => b.lignes.map((l) => `${l.designation} × ${qte(l.quantite)}`).join(", ") },
    {
      key: "statut",
      header: k("statut"),
      sortValue: (b) => b.statut_label,
      render: (b) => (
        <>
          <Badge tone={b.statut === "receptionne" ? "ok" : "warn"}>{statutLabel("transfert", b.statut, b.statut_label)}</Badge> {b.reserves}
        </>
      ),
    },
    {
      key: "__actions",
      header: <span className="sr-only">{actionsHeader}</span>,
      render: (b) => (
        <LigneActions
          actions={[
            ...(b.statut === "prepare" ? [{ label: k("transferts.expedier"), path: `/api/operations/transferts/${b.id}/expedier/` }] : []),
            ...(b.statut === "expedie"
              ? [{ label: k("transferts.receptionner"), path: `/api/operations/transferts/${b.id}/receptionner/`, prompt: { name: "reserves", label: k("transferts.reserves") } }]
              : []),
          ]}
          pdf={{ path: `/api/operations/transferts/${b.id}/?export=pdf`, name: `${b.code}.pdf` }}
        />
      ),
    },
  ];
  const colsAttachements: Column<AttachementRow>[] = [
    {
      key: "code",
      header: k("code"),
      sortValue: (a) => a.code,
      render: (a) => (
        <>
          {a.code} {a.situation_code ? <span className="muted">· {a.situation_code}</span> : null}
        </>
      ),
    },
    { key: "of", header: k("of"), sortValue: (a) => a.ordre_code, render: (a) => a.ordre_code },
    { key: "designation", header: k("attachements.designation"), render: (a) => a.designation },
    { key: "quantite", header: k("attachements.quantite"), num: true, render: (a) => `${qte(a.quantite)} ${a.unite}` },
    { key: "montant", header: k("attachements.montant"), num: true, sortValue: (a) => (a.montant === null ? null : Number(a.montant)), render: (a) => fcfa(a.montant) },
    {
      key: "statut",
      header: k("statut"),
      sortValue: (a) => a.statut_label,
      render: (a) => (
        <>
          <Badge tone={a.statut === "signe" ? "ok" : "warn"}>{statutLabel("attachement", a.statut, a.statut_label)}</Badge> {a.signataire_client}
        </>
      ),
    },
    actionsColumn<AttachementRow>(actionsHeader, (a) =>
      a.statut === "brouillon"
        ? [{ label: k("attachements.signer"), path: `/api/operations/attachements/${a.id}/signer/`, prompt: { name: "signataire_client", label: k("attachements.signataire") } }]
        : [],
    ),
  ];
  const colsSituations: Column<Situation>[] = [
    {
      key: "situation",
      header: k("attachements.situation"),
      sortValue: (s) => s.code,
      render: (s) => (
        <>
          <span className="cell-nowrap">{s.code}</span> · {s.label}
        </>
      ),
    },
    {
      key: "statut",
      header: k("statut"),
      sortValue: (s) => s.status,
      render: (s) => (
        <Badge tone={s.status === "facturee" || s.status === "validee" ? "ok" : "warn"}>{statutLabel("situation", s.status, s.status_label)}</Badge>
      ),
    },
    { key: "montant", header: k("attachements.montant"), num: true, sortValue: (s) => (s.amount === null ? null : Number(s.amount)), render: (s) => fcfa(s.amount) },
    { key: "montantAtt", header: k("attachements.montantAtt"), num: true, render: (s) => fcfa(s.montant_attachements) },
    { key: "recu", header: k("attachements.recu"), sortValue: (s) => s.recue_le, render: (s) => (s.recue_le ? `${formatDate(s.recue_le)} · ${s.recue_signataire}` : "—") },
    sansRetour(actionsColumn<Situation>(actionsHeader, (s) => [
      ...(s.status === "brouillon" || s.status === "soumise"
        ? [{ label: k("attachements.valoriser"), path: `/api/operations/situations/${s.id}/valoriser-attachements/` }]
        : []),
      ...((s.status === "validee" || s.status === "facturee") && !s.recue_le
        ? [{ label: k("attachements.accuser"), path: `/api/operations/situations/${s.id}/accuser-reception/`, prompt: { name: "recue_signataire", label: k("attachements.signataire") } }]
        : []),
    ])),
  ];
  const colsPointages: Column<Pointage>[] = [
    { key: "code", header: k("code"), sortValue: (p) => p.code, render: (p) => <span className="cell-nowrap">{p.code}</span> },
    { key: "of", header: k("of"), sortValue: (p) => p.ordre_code, render: (p) => <span className="cell-nowrap">{p.ordre_code}</span> },
    { key: "salarie", header: k("pointages.salarie"), sortValue: (p) => p.worker_name_filled, render: (p) => p.worker_name_filled ?? "—" },
    { key: "date", header: k("date"), sortValue: (p) => p.date, render: (p) => <span className="cell-nowrap">{formatDate(p.date)}</span> },
    {
      key: "heures",
      header: k("pointages.heures"),
      num: true,
      sortValue: (p) => Number(p.hours),
      render: (p) => (
        <>
          <span className="cell-nowrap">{formatNumber(Number(p.hours), { decimals: decimales(p.hours) })} h</span>
          {p.hours_type && p.hours_type !== "normal" ? <span className="cell-sub">{statutLabel("heures", p.hours_type, p.hours_type_label)}</span> : null}
        </>
      ),
    },
    { key: "nature", header: k("pointages.nature"), render: (p) => (p.nature_mo ? statutLabel("nature", p.nature_mo, p.nature_mo_label) : p.nature_mo_label) },
    {
      key: "statut",
      header: k("statut"),
      sortValue: (p) => p.status,
      render: (p) => <Badge tone={p.status === "saisi" ? "warn" : "ok"}>{statutLabel("pointage", p.status, p.status_label)}</Badge>,
    },
    sansRetour(actionsColumn<Pointage>(actionsHeader, (p) => [
      ...(p.status === "saisi" ? [{ label: k("pointages.valider"), path: `/api/operations/pointages/${p.id}/valider/` }] : []),
      ...(p.status === "valide" ? [{ label: k("pointages.transferer"), path: `/api/operations/pointages/${p.id}/transferer-paie/` }] : []),
    ])),
  ];
  const colsMarges: Column<AffaireLigne>[] = [
    { key: "affaire", header: k("affaire"), sortValue: (a) => a.affaire_code, render: (a) => `${a.affaire_code} · ${a.affaire_label}` },
    { key: "avancement", header: k("suivi.avancement"), num: true, sortValue: (a) => nombre(a.avancement_pct), render: (a) => pct(a.avancement_pct) },
    { key: "ca", header: k("suivi.ca"), num: true, sortValue: (a) => nombre(a.chiffre_affaires), render: (a) => fcfa(a.chiffre_affaires) },
    { key: "engage", header: k("suivi.engage"), num: true, sortValue: (a) => nombre(a.couts_engages), render: (a) => fcfa(a.couts_engages) },
    { key: "cat", header: k("suivi.cat"), num: true, sortValue: (a) => nombre(a.cout_a_terminaison), render: (a) => fcfa(a.cout_a_terminaison) },
    {
      key: "marge",
      header: k("suivi.marge"),
      num: true,
      sortValue: (a) => nombre(a.marge_a_terminaison),
      render: (a) => (
        <>
          {fcfa(a.marge_a_terminaison)} {a.marge_pct !== null && <span className="muted">({pct(a.marge_pct)})</span>}
        </>
      ),
    },
  ];
  const colsOrdres: Column<Of>[] = [
    {
      key: "of",
      header: k("of"),
      sortValue: (o) => o.code,
      render: (o) => (
        <>
          <span className="cell-nowrap">{o.code}</span> · {o.label}
        </>
      ),
    },
    {
      key: "statut",
      header: k("statut"),
      sortValue: (o) => o.status,
      render: (o) => (
        <Badge tone={o.status === "en_cours" ? "warn" : o.status === "termine" || o.status === "cloture" ? "ok" : o.status === "annule" ? "err" : "brand"}>
          {statutLabel("of", o.status, o.status_label)}
        </Badge>
      ),
    },
    {
      key: "avancement",
      header: k("suivi.avancement"),
      num: true,
      render: (o) => pct(suivi?.ordres.find((x) => x.ordre === o.id)?.avancement_pct ?? null),
    },
    {
      key: "periode",
      header: k("suivi.periode"),
      sortValue: (o) => o.planned_start,
      render: (o) => (
        <>
          <span className="cell-nowrap">
            {o.planned_start ? formatDate(o.planned_start) : "—"} → {o.planned_end ? formatDate(o.planned_end) : "—"}
          </span>
          {o.motif_replanification ? <span className="cell-sub">{o.motif_replanification}</span> : null}
        </>
      ),
    },
    {
      key: "__actions",
      header: <span className="sr-only">{actionsHeader}</span>,
      render: (o) => {
        const actif = o.status === "prevu" || o.status === "lance" || o.status === "en_cours";
        return (
          <LigneActions
            actions={
              actif
                ? [
                    { label: k("suivi.verifier"), path: `/api/operations/ordres/${o.id}/verifier-besoins/` },
                    {
                      label: k("suivi.replanifier"),
                      path: `/api/operations/ordres/${o.id}/replanifier/`,
                      body: { motif: k("suivi.motifReplan") },
                      prompt: { name: "decalage_jours", label: k("suivi.decalage") },
                    },
                  ]
                : []
            }
            pdf={{ path: `/api/operations/ordres/${o.id}/?export=pdf`, name: `${o.code}.pdf` }}
          />
        );
      },
    },
  ];
  const colsCharge: Column<ChargeLigne>[] = [
    { key: "date", header: k("date"), sortValue: (l) => l.date, render: (l) => <span className="cell-nowrap">{formatDate(l.date)}</span> },
    { key: "perimetre", header: k("charge.perimetre"), sortValue: (l) => l.scope, render: (l) => perimetre(l.scope) },
    { key: "ressource", header: k("charge.ressource"), render: (l) => k(`charge.${l.resource}`) },
    {
      key: "planifie",
      header: k("charge.planifie"),
      num: true,
      sortValue: (l) => Number(l.planned_hours),
      render: (l) => (
        <>
          {l.overload && l.capacity !== null && Number(l.capacity) > 0 ? (
            <Badge tone="warn" title={k("charge.surcharge")}>
              +{formatNumber(Math.round((Number(l.planned_hours) / Number(l.capacity) - 1) * 100))} %
            </Badge>
          ) : null}{" "}
          <span className="cell-nowrap">{formatNumber(Number(l.planned_hours))} h</span>
        </>
      ),
    },
    { key: "capacite", header: k("charge.capacite"), num: true, render: (l) => (l.capacity === null ? "—" : `${formatNumber(Number(l.capacity))} h`) },
  ];
  const colsRegistre: Column<Registre>[] = [
    {
      key: "document",
      header: k("registre.document"),
      sortValue: (d) => d.titre,
      render: (d) => {
        const m = RAPPORT_EXEC.exec(d.titre);
        return (
          <>
            {m ? t("revueR2.operations.registre.rapport", { code: m[1] }) : d.titre}
            {d.reference && !d.titre.includes(d.reference) ? <span className="muted"> {d.reference}</span> : null}
          </>
        );
      },
    },
    {
      key: "type",
      header: k("registre.type"),
      render: (d) => {
        if (!d.type) return "—";
        const type = sansModule(d.type);
        return type === "Rapports d'exécution" ? t("revueR2.operations.registre.typeRapports") : type;
      },
    },
    { key: "objet", header: k("registre.objet"), render: (d) => d.objet },
    { key: "date", header: k("date"), sortValue: (d) => d.lie_le, render: (d) => <span className="cell-nowrap">{formatDate(d.lie_le)}</span> },
  ];
  const colsDossiers: Column<Dossier>[] = [
    { key: "dossier", header: k("registre.dossier"), sortValue: (d) => d.ordre_code, render: (d) => d.ordre_code },
    { key: "empreinte", header: k("registre.empreinte"), render: (d) => <code title={d.sha256}>{d.sha256.slice(0, 16)}…</code> },
    { key: "conservation", header: k("registre.conservation"), num: true, render: (d) => t("ecarts_m3.registre.ans", { n: d.retention_years }) },
    { key: "date", header: k("date"), sortValue: (d) => d.created_at, render: (d) => formatDate(d.created_at) },
  ];

  return (
    <>
      <SectionCard title={k("parametres.title")} subtitle={t("tableaux.operations.nbParametres", { count: parametres.length })}>
        {provisoires > 0 && (
          <p data-testid="m3-provisoire">
            <Badge tone="warn">{t("tableaux.operations.provisoire")}</Badge> {t("ecarts_m3.parametres.bandeau", { n: provisoires })}
          </p>
        )}
        <div data-testid="m3-parametres">
          <DataTable columns={colsParametres} rows={parametres} caption={k("parametres.title")} emptyLabel={t("tableaux.operations.aucunParametre")} />
        </div>
      </SectionCard>

      <SectionCard
        title={k("preparation.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={k("preparation.fiche")}
              endpoint="/api/operations/fiches-preparation/"
              fields={[
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                { name: "outillage", label: k("preparation.outillage"), type: "textarea" },
                { name: "consignes", label: k("preparation.consignes"), type: "textarea" },
              ]}
            />
            <QuickForm
              title={k("preparation.besoin")}
              endpoint="/api/operations/besoins-matiere/"
              fields={[
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                { name: "article", label: k("preparation.article"), type: "select", options: articleOpts, required: true },
                { name: "quantite", label: k("preparation.quantite"), type: "number", min: 0, step: "0.01", required: true },
              ]}
            />
          </SectionActions>
        }
      >
        <h4>{t("tableaux.operations.fichesPreparation")}</h4>
        <div data-testid="m3-fiches-preparation">
          <DataTable columns={colsFiches} rows={fiches} caption={t("tableaux.operations.fichesPreparation")} emptyLabel={t("tableaux.operations.aucuneFiche")} />
        </div>
        <h4>{t("tableaux.operations.besoinsMatiere")}</h4>
        <div data-testid="m3-besoins">
          <DataTable columns={colsBesoins} rows={besoins} caption={t("tableaux.operations.besoinsMatiere")} emptyLabel={t("tableaux.operations.aucunBesoin")} />
        </div>
        <p className="muted">{k("preparation.note")}</p>
      </SectionCard>

      <SectionCard
        title={k("rapports.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={k("rapports.ajouter")}
              endpoint="/api/operations/rapports/"
              fields={[
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                {
                  name: "type", label: k("rapports.type"), type: "select", required: true, defaultValue: "execution",
                  options: [
                    { value: "execution", label: k("rapports.execution") },
                    { value: "avancement", label: k("rapports.avancement") },
                  ],
                },
                { name: "date", label: k("date"), type: "date", required: true },
                { name: "quantite_realisee", label: k("rapports.realise"), type: "number", min: 0, step: "0.01" },
                { name: "quantite_rebut", label: k("rapports.rebut"), type: "number", min: 0, step: "0.01" },
                { name: "avancement", label: k("rapports.pct"), type: "number", min: 0 },
                { name: "observations", label: k("rapports.observations"), type: "textarea" },
              ]}
            />
            <QuickForm
              title={k("controle.ajouter")}
              endpoint="/api/operations/fiches-controle/"
              fields={[
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                { name: "date", label: k("date"), type: "date", required: true },
                { name: "objet", label: k("controle.objet"), required: true },
                { name: "points", label: k("controle.points"), type: "textarea", required: true },
              ]}
              transform={(v) => ({
                ...v,
                points: (v.points ?? "")
                  .split("\n")
                  .map((l) => l.trim())
                  .filter(Boolean)
                  .map((l) => ({ libelle: l.replace(/^!\s*/, ""), conforme: !l.startsWith("!") })),
              })}
            />
          </SectionActions>
        }
      >
        <h4>{t("tableaux.operations.rapports")}</h4>
        <div data-testid="m3-rapports">
          <DataTable columns={colsRapports} rows={rapports} caption={t("tableaux.operations.rapports")} emptyLabel={t("tableaux.operations.aucunRapport")} />
        </div>
        <h4>{t("tableaux.operations.fichesControle")}</h4>
        <div data-testid="m3-fiches-controle">
          <DataTable columns={colsControles} rows={controles} caption={t("tableaux.operations.fichesControle")} emptyLabel={t("tableaux.operations.aucunControle")} />
        </div>
        <p className="muted">{k("rapports.note")}</p>
      </SectionCard>

      <SectionCard
        title={k("transferts.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={k("transferts.ajouter")}
              endpoint="/api/operations/transferts/"
              fields={[
                {
                  name: "type", label: k("transferts.type"), type: "select", required: true, defaultValue: "bl",
                  options: [
                    { value: "bl", label: k("transferts.bl") },
                    { value: "transfert", label: k("transferts.fiche") },
                  ],
                },
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                { name: "destination", label: k("transferts.destination"), required: true },
                { name: "transporteur", label: k("transferts.transporteur") },
                { name: "lignes", label: k("transferts.lignes"), type: "textarea", required: true },
              ]}
              transform={(v) => ({
                ...v,
                lignes: (v.lignes ?? "")
                  .split("\n")
                  .map((l) => l.trim())
                  .filter(Boolean)
                  .map((l) => {
                    const [designation, quantite] = l.split(";").map((x) => x.trim());
                    return { designation, quantite: quantite || "1" };
                  }),
              })}
            />
          </SectionActions>
        }
      >
        <div data-testid="m3-transferts">
          <DataTable columns={colsTransferts} rows={transferts} caption={k("transferts.title")} emptyLabel={t("tableaux.operations.aucunTransfert")} />
        </div>
      </SectionCard>

      <SectionCard
        title={k("attachements.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={k("attachements.ajouter")}
              endpoint="/api/operations/attachements/"
              fields={[
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                { name: "situation", label: k("attachements.situation"), type: "select", options: situationOpts },
                { name: "date", label: k("date"), type: "date", required: true },
                { name: "designation", label: k("attachements.designation"), required: true },
                { name: "unite", label: k("attachements.unite"), defaultValue: "ml" },
                { name: "quantite", label: k("attachements.quantite"), type: "number", min: 0, step: "0.001", required: true },
                { name: "prix_unitaire", label: k("attachements.prix"), type: "number", min: 0 },
              ]}
            />
            <QuickForm
              title={k("attachements.repartition")}
              endpoint="/api/operations/repartitions/"
              fields={[
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                { name: "affaire", label: k("affaire"), type: "select", options: affaireOpts, required: true },
                { name: "part_pct", label: k("attachements.part"), type: "number", min: 1, required: true },
              ]}
            />
          </SectionActions>
        }
      >
        <h4>{t("tableaux.operations.attachements")}</h4>
        <div data-testid="m3-attachements">
          <DataTable columns={colsAttachements} rows={attachements} caption={t("tableaux.operations.attachements")} emptyLabel={t("tableaux.operations.aucunAttachement")} />
        </div>
        <h4>{t("tableaux.operations.situations")}</h4>
        <div data-testid="m3-situations-recu">
          <DataTable columns={colsSituations} rows={pageSituations.rows} pagination={pageSituations.pagination} caption={t("tableaux.operations.situations")} emptyLabel={t("tableaux.operations.aucuneSituation")} />
        </div>
      </SectionCard>

      <SectionCard
        title={k("pointages.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={k("pointages.ajouter")}
              endpoint="/api/operations/pointages/"
              fields={[
                { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
                { name: "employe", label: k("pointages.salarie"), type: "select", options: employeOpts },
                { name: "worker_name", label: k("pointages.nomLibre") },
                { name: "date", label: k("date"), type: "date", required: true },
                { name: "hours", label: k("pointages.heures"), type: "number", min: 0, step: "0.25", required: true },
                {
                  name: "hours_type", label: k("pointages.type"), type: "select", defaultValue: "normal",
                  options: ["normal", "supplementaire", "nuit", "astreinte"].map((v) => ({ value: v, label: k(`pointages.types.${v}`) })),
                },
                {
                  name: "nature_mo", label: k("pointages.nature"), type: "select", defaultValue: "directe",
                  options: [
                    { value: "directe", label: k("pointages.directe") },
                    { value: "indirecte", label: k("pointages.indirecte") },
                  ],
                },
              ]}
            />
          </SectionActions>
        }
      >
        <div data-testid="m3-pointages">
          <DataTable columns={colsPointages} rows={pagePointages.rows} pagination={pagePointages.pagination} caption={k("pointages.title")} density="compact" emptyLabel={t("tableaux.operations.aucunPointage")} />
        </div>
        <p className="muted">{k("pointages.note")}</p>
      </SectionCard>

      <SectionCard
        title={k("suivi.title")}
        actions={
          <SectionActions>
            <ActionBar actions={[{ label: k("suivi.publier"), path: "/api/operations/ordres/publier-marges/", confirm: k("suivi.publierQ") }]} />
            <Menu
              label={t("tableaux.operations.rapportsPeriodiques")}
              items={[
                { label: k("suivi.hebdoPdf"), icon: FileDown, onSelect: () => telecharger("/api/operations/ordres/rapport-periodique/?periode=hebdo&export=pdf", "rapport-hebdo.pdf") },
                { label: k("suivi.mensuelPdf"), icon: FileDown, onSelect: () => telecharger("/api/operations/ordres/rapport-periodique/?periode=mensuel&export=pdf", "rapport-mensuel.pdf") },
                { label: k("suivi.mensuelXlsx"), icon: FileDown, onSelect: () => telecharger("/api/operations/ordres/rapport-periodique/?periode=mensuel&export=xlsx", "rapport-mensuel.xlsx") },
              ]}
              trigger={
                <button type="button" className="btn ghost">
                  <FileDown size={14} aria-hidden="true" /> {t("tableaux.operations.rapportsPeriodiques")}
                </button>
              }
            />
          </SectionActions>
        }
      >
        {ind && (
          <div className="kpi-grid">
            <Kpi label={k("suivi.productivite")} value={pct(ind.productivite_pct)} tone="brand" delay={0} />
            <Kpi label={k("suivi.rebut")} value={pct(ind.taux_rebut_pct)} tone="accent" delay={0.03} />
            <Kpi label={k("suivi.directe")} value={`${formatNumber(Number(ind.heures_directes))} h`} hint={`${formatNumber(Number(ind.heures_indirectes))} h ${k("suivi.indirecte")}`} tone="brand" delay={0.06} />
            <Kpi label={k("suivi.retards")} value={ind.of_en_retard} hint={`${ind.ruptures_ouvertes} ${k("suivi.ruptures")}`} tone="accent" delay={0.09} />
          </div>
        )}
        <h4>{t("tableaux.operations.margesAffaire")}</h4>
        <div data-testid="m3-marges">
          <DataTable
            columns={colsMarges}
            rows={(suivi?.affaires ?? []).map((a) => ({ ...a, id: a.affaire }))}
            caption={t("tableaux.operations.margesAffaire")}
            emptyLabel={t("tableaux.operations.aucuneMarge")}
          />
        </div>
        <p className="muted">{t("ecarts_m3.suivi.note", { m: suivi?.methode ?? 1 })}</p>
        <h4>{t("tableaux.operations.ordres")}</h4>
        <div data-testid="m3-of-impressions">
          <DataTable columns={colsOrdres} rows={pageOrdres.rows} pagination={pageOrdres.pagination} caption={t("tableaux.operations.ordres")} emptyLabel={t("tableaux.operations.aucunOrdre")} />
        </div>
      </SectionCard>

      <SectionCard
        title={k("charge.title")}
        actions={
          <SectionActions>
            <ActionBar actions={[{ label: k("charge.escalader"), path: "/api/operations/ordres/escalader-surcharges/", confirm: k("charge.escaladerQ") }]} />
          </SectionActions>
        }
      >
        <div data-testid="m3-charge-jour">
          <DataTable
            columns={colsCharge}
            rows={pageCharge.rows}
            pagination={pageCharge.pagination}
            caption={k("charge.title")}
            density="compact"
            emptyLabel={t("tableaux.operations.aucuneCharge")}
          />
        </div>
        {escalades.length > 0 && (
          <ul data-testid="m3-escalades">
            {escalades.map((e) => (
              <li key={e.id}>
                <Badge tone="warn">{k("charge.escalade")}</Badge> {perimetre(e.scope)} · {k(`charge.${e.resource}`)} · {formatDate(e.semaine)} : +{formatNumber(Number(e.surcharge_pct))} %
              </li>
            ))}
          </ul>
        )}
        <p className="muted">{k("charge.note")}</p>
      </SectionCard>

      <SectionCard title={k("registre.title")}>
        <div data-testid="m3-registre">
          <DataTable columns={registre.every((d) => d.objet === d.titre) ? colsRegistre.filter((c) => c.key !== "objet") : colsRegistre} rows={registre} caption={k("registre.title")} emptyLabel={t("tableaux.operations.aucunDocument")} />
        </div>
        <h4>{t("tableaux.operations.dossiers")}</h4>
        <div data-testid="m3-dossiers">
          <DataTable columns={colsDossiers} rows={dossiers} caption={t("tableaux.operations.dossiers")} emptyLabel={t("tableaux.operations.aucunDossier")} />
        </div>
      </SectionCard>
    </>
  );
}
