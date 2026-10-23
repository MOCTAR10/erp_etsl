import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, QuickForm, SectionCard } from "../ui";
import { actionsColumn } from "../ui/DataTable";

interface Parametre {
  id: number;
  cle: string;
  libelle: string;
  valeur: unknown;
  provisoire: boolean;
}
interface Completude {
  requises: string[];
  manquantes: string[];
  complet: boolean;
  taux_pct: string;
}
interface Contentieux {
  id: string;
  code: string;
  objet: string;
  nature: string;
  phase: string;
  phase_label: string;
  statut: string;
  juridiction: string;
  probabilite: string | null;
  probabilite_label: string;
  completude: Completude;
}
interface Convention {
  id: string;
  code: string;
  titre: string;
  completude: Completude;
}
interface Jalon {
  id: string;
  contentieux_code: string;
  libelle: string;
  date_prevue: string;
  date_realisee: string | null;
  statut: string;
  statut_label: string;
  days_left: number;
}
interface ActionJournal {
  id: string;
  contentieux_code: string;
  date_action: string;
  type_label: string;
  description: string;
  auteur_name: string | null;
}
interface LigneRisque {
  id: string;
  code: string;
  objet: string;
  juridiction: string;
  phase: string;
  probabilite: string | null;
  probabilite_pct: number | null;
  niveau: "eleve" | "moyen" | "faible" | "non_cote";
  montant_en_jeu: string | null;
  exposition: string | null;
}
interface VueRisque {
  contentieux: LigneRisque[];
  par_niveau: Record<string, number>;
  total_enjeu: string | null;
  total_exposition: string | null;
  cautions_en_cours: number;
  engagements_cautions: string | null;
}
interface Garantie {
  id: string;
  code: string;
  type_label: string;
  statut: string;
  statut_label: string;
  date_echeance: string;
  en_attente_dg: boolean;
  beneficiaire?: string;
  numero_police?: string;
}
interface Alerte {
  type: string;
  code: string;
  libelle: string;
  date_echeance: string;
  bande: string;
  jours: number;
}
interface Alertes {
  contrats_m1: Alerte[];
  jalons: Alerte[];
  mandats_gr: Alerte[];
}
interface DossierGr {
  id: string;
  code: string;
  objet: string;
  statut: string;
  mandat_reference: string;
  mandat_date_fin: string | null;
  date_revue: string | null;
  controle: { a_jour: boolean; motifs: string[]; tarifs_en_vigueur: number; completude: Completude };
}
interface TypeDoc {
  id: string;
  label: string;
  retention_years: number | null;
  retention_provisoire: boolean;
}
interface Candidat {
  id: string;
  title: string;
  type_label: string;
  fin_retention: string;
}
interface Purge {
  id: string;
  document_title: string;
  type_label: string;
  fin_retention: string;
  statut: string;
  statut_label: string;
  motif: string;
}
interface DocRef {
  id: string;
  title: string;
}

const PHASES = ["pre_contentieux", "tribunal", "arbitrage", "appel"];
const PROBAS = ["faible", "moyenne", "forte", "certaine"];
const TYPES_ACTION = ["audience", "conclusions", "courrier", "expertise", "negociation", "decision", "autre"];
const NIVEAU_TONE = { eleve: "err", moyen: "warn", faible: "ok", non_cote: "brand" } as const;
const fcfa = (v: string | null) => (v === null ? "—" : formatMoney(Number(v)));
const rows = <T,>(p: T[] | { results: T[] } | undefined): T[] => (Array.isArray(p) ? p : (p?.results ?? []));

function useListe<T>(key: string, path: string): T[] {
  return useQuery({ queryKey: ["m12e", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

function CompletudeCell({ c }: { c: Completude }) {
  const { t } = useTranslation();
  return (
    <>
      <Badge tone={c.complet ? "ok" : "warn"}>{c.taux_pct} %</Badge>{" "}
      {c.manquantes.length > 0 && <span className="muted">{t("ecarts_m12.manquantes")} : {c.manquantes.join(", ")}</span>}
    </>
  );
}

/** Valeur d'un paramètre lisible (liste, dictionnaire ou scalaire), sans JSON brut à l'écran. */
function valeurLisible(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.map(valeurLisible).join(", ");
  if (typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, x]) => `${k} : ${valeurLisible(x)}`)
      .join(" · ");
  }
  return String(v);
}

/** Ligne de la grille « dossiers » : contentieux (qualifiables) et conventions (complétude seule). */
type DossierLigne = { id: string; libelle: string; completude: Completude; contentieux: Contentieux | null };

/** Écarts M12 : paramètres provisoires, dossiers complets, suivi contentieux, vue des risques, validation DG, GR, archivage. */
export function EcartsM12Section() {
  const { t } = useTranslation();
  const params = useListe<Parametre>("params", "/api/juridique/parametres/");
  const contentieux = useListe<Contentieux>("contentieux", "/api/juridique/contentieux/");
  const conventions = useListe<Convention>("conventions", "/api/juridique/conventions/");
  const jalons = useListe<Jalon>("jalons", "/api/juridique/jalons/");
  const journal = useListe<ActionJournal>("journal", "/api/juridique/actions-contentieux/");
  const cautions = useListe<Garantie>("cautions", "/api/juridique/cautions/");
  const assurances = useListe<Garantie>("assurances", "/api/juridique/assurances/");
  const dossiersGr = useListe<DossierGr>("gr", "/api/juridique/dossiers-gr/");
  const types = useListe<TypeDoc>("types", "/api/documents/types/");
  const risques = useQuery({ queryKey: ["m12e", "risques"], queryFn: () => api.get<VueRisque>("/api/juridique/risques/"), retry: 0 }).data;
  const alertes = useQuery({ queryKey: ["m12e", "alertes"], queryFn: () => api.get<Alertes>("/api/juridique/alertes/"), retry: 0 }).data;
  const candidats = useQuery({ queryKey: ["m12e", "candidats"], queryFn: () => api.get<Candidat[]>("/api/documents/purges/candidats/"), retry: 0 }).data ?? [];
  const purges = useQuery({ queryKey: ["m12e", "purges"], queryFn: () => api.listAll<Purge>("/api/documents/purges/"), retry: 0 }).data ?? [];
  const docs = rows(
    useQuery({
      queryKey: ["m12e", "docs"],
      queryFn: () => api.get<DocRef[] | { results: DocRef[] }>("/api/documents/documents/?page_size=100"),
      retry: 0,
    }).data,
  );
  const juridictions = (params.find((p) => p.cle === "juridictions")?.valeur as string[] | undefined) ?? [];
  const provisoires = params.filter((p) => p.provisoire).length;
  const contOpts = contentieux.map((c) => ({ value: c.id, label: `${c.code} · ${c.objet}` }));
  const dossierOpts = [
    ...contentieux.map((c) => ({ value: `contentieux:${c.id}`, label: `${t("ecarts_m12.dossiers.contentieux")} ${c.code}` })),
    ...conventions.map((c) => ({ value: `convention:${c.id}`, label: `${t("ecarts_m12.dossiers.convention")} ${c.code}` })),
    ...dossiersGr.map((d) => ({ value: `gr:${d.id}`, label: `${t("ecarts_m12.dossiers.gr")} ${d.code}` })),
  ];
  const alertesExtra = (alertes ? [...alertes.contrats_m1, ...alertes.jalons, ...alertes.mandats_gr] : []).map((a) => ({ ...a, id: `${a.type}-${a.code}-${a.libelle}` }));
  const garanties = [
    ...cautions.map((c) => ({ ...c, kind: "cautions" as const, label: `${c.type_label} · ${c.beneficiaire ?? ""}` })),
    ...assurances.map((a) => ({ ...a, kind: "assurances" as const, label: `${a.type_label} · ${a.numero_police ?? ""}` })),
  ];
  type GarantieLigne = (typeof garanties)[number];
  const dossiers: DossierLigne[] = [
    ...contentieux.map((c) => ({ id: c.id, libelle: `${c.code} · ${c.objet}`, completude: c.completude, contentieux: c })),
    ...conventions.map((c) => ({ id: c.id, libelle: `${c.code} · ${c.titre}`, completude: c.completude, contentieux: null })),
  ];

  return (
    <div data-testid="ecarts-m12">
      <SectionCard title={t("ecarts_m12.parametres.title")}>
        {provisoires > 0 && (
          <p className="action-error" role="note" data-testid="m12-provisoire">
            {t("ecarts_m12.parametres.bandeau", { count: provisoires })}
          </p>
        )}
        <div data-testid="m12-parametres">
          <DataTable
            caption={t("ecarts_m12.parametres.title")}
            rows={params}
            density="compact"
            columns={[
              { key: "libelle", header: t("tableaux.juridique.parametre"), render: (p) => p.libelle, sortValue: (p) => p.libelle },
              { key: "valeur", header: t("tableaux.juridique.valeur"), render: (p) => <span className="muted">{valeurLisible(p.valeur)}</span> },
              {
                key: "statut",
                header: t("tableaux.juridique.statut"),
                render: (p) => <Badge tone={p.provisoire ? "warn" : "ok"}>{p.provisoire ? t("ecarts_m12.provisoire") : t("ecarts_m12.confirme")}</Badge>,
              },
              actionsColumn<Parametre>(t("ui.actions"), (p) => [
                { label: t("ecarts_m12.parametres.modifier"), path: `/api/juridique/parametres/${p.id}/modifier/`, tone: "ghost" as const, prompt: { name: "valeur", label: t("ecarts_m12.parametres.json") } },
                ...(p.provisoire
                  ? [{ label: t("ecarts_m12.parametres.confirmer"), path: `/api/juridique/parametres/${p.id}/confirmer/`, confirm: t("ecarts_m12.parametres.confirmerQ") }]
                  : []),
              ]),
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m12.contentieux.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("ecarts_m12.contentieux.action")}
              endpoint="/api/juridique/actions-contentieux/"
              fields={[
                { name: "contentieux", label: t("ecarts_m12.contentieux.dossier"), type: "select", required: true, options: contOpts },
                { name: "type", label: t("ecarts_m12.contentieux.type"), type: "select", required: true, defaultValue: "audience", options: TYPES_ACTION.map((v) => ({ value: v, label: t(`ecarts_m12.typesAction.${v}`) })) },
                { name: "date_action", label: t("ecarts_m12.contentieux.date"), type: "date" },
                { name: "description", label: t("ecarts_m12.contentieux.description"), type: "textarea", required: true },
              ]}
            />
            <QuickForm
              title={t("ecarts_m12.contentieux.jalon")}
              endpoint="/api/juridique/jalons/"
              fields={[
                { name: "contentieux", label: t("ecarts_m12.contentieux.dossier"), type: "select", required: true, options: contOpts },
                { name: "libelle", label: t("ecarts_m12.contentieux.libelle"), required: true },
                { name: "date_prevue", label: t("ecarts_m12.contentieux.datePrevue"), type: "date", required: true },
              ]}
            />
            <QuickForm
              title={t("ecarts_m12.pieces.ajouter")}
              endpoint="/api/juridique/pieces/"
              fields={[
                { name: "dossier", label: t("ecarts_m12.pieces.dossier"), type: "select", required: true, options: dossierOpts },
                { name: "piece", label: t("ecarts_m12.pieces.piece"), required: true },
                { name: "document", label: t("ecarts_m12.pieces.document"), type: "select", required: true, options: docs.map((d) => ({ value: d.id, label: d.title })) },
              ]}
              transform={(v) => {
                const [dossier_type, dossier_id] = (v.dossier ?? "").split(":");
                return { dossier_type, dossier_id, piece: v.piece, document: v.document };
              }}
            />
          </SectionActions>
        }
      >
        <div data-testid="m12-contentieux">
          <DataTable
            caption={t("ecarts_m12.contentieux.title")}
            rows={dossiers}
            columns={[
              { key: "dossier", header: t("ecarts_m12.contentieux.dossier"), render: (d) => d.libelle, sortValue: (d) => d.libelle },
              {
                key: "juridiction",
                header: t("ecarts_m12.contentieux.juridiction"),
                render: (d) => (d.contentieux ? d.contentieux.juridiction || "—" : <span className="muted">{t("ecarts_m12.dossiers.convention")}</span>),
              },
              { key: "phase", header: t("ecarts_m12.contentieux.phase"), render: (d) => d.contentieux?.phase_label ?? "—" },
              { key: "probabilite", header: t("ecarts_m12.contentieux.probabilite"), render: (d) => (d.contentieux?.probabilite ? d.contentieux.probabilite_label : "—") },
              { key: "completude", header: t("ecarts_m12.completude"), render: (d) => <CompletudeCell c={d.completude} /> },
              actionsColumn<DossierLigne>(t("ui.actions"), (d) => {
                const c = d.contentieux;
                if (!c || (c.statut !== "ouvert" && c.statut !== "en_instruction")) return [];
                return [
                  { label: t("ecarts_m12.contentieux.juridiction"), path: `/api/juridique/contentieux/${c.id}/qualifier/`, tone: "ghost" as const, prompt: { name: "juridiction", label: t("ecarts_m12.contentieux.juridiction"), options: juridictions.map((j) => ({ value: j, label: j })) } },
                  { label: t("ecarts_m12.contentieux.coter"), path: `/api/juridique/contentieux/${c.id}/qualifier/`, tone: "ghost" as const, prompt: { name: "probabilite", label: t("ecarts_m12.contentieux.probabilite"), options: PROBAS.map((v) => ({ value: v, label: t(`ecarts_m12.probas.${v}`) })) } },
                  { label: t("ecarts_m12.contentieux.phaseSuivante"), path: `/api/juridique/contentieux/${c.id}/avancer-phase/`, tone: "ghost" as const, prompt: { name: "phase", label: t("ecarts_m12.contentieux.phase"), options: PHASES.filter((p) => p !== c.phase).map((v) => ({ value: v, label: t(`ecarts_m12.phases.${v}`) })) } },
                ];
              }),
            ]}
          />
        </div>
        <h4>{t("ecarts_m12.contentieux.echeancier")}</h4>
        <div data-testid="m12-jalons">
          <DataTable
            caption={t("ecarts_m12.contentieux.echeancier")}
            rows={jalons}
            density="compact"
            initialSort={{ id: "date", desc: false }}
            columns={[
              { key: "dossier", header: t("ecarts_m12.contentieux.dossier"), render: (j) => j.contentieux_code },
              { key: "jalon", header: t("ecarts_m12.contentieux.libelle"), render: (j) => j.libelle },
              {
                key: "date",
                header: t("ecarts_m12.contentieux.datePrevue"),
                sortValue: (j) => j.date_prevue,
                render: (j) => (
                  <>
                    {formatDate(j.date_prevue)}
                    {j.statut === "a_venir" ? <span className="muted"> · {j.days_left} {t("juridique.jours")}</span> : null}
                  </>
                ),
              },
              {
                key: "statut",
                header: t("tableaux.juridique.statut"),
                render: (j) => <Badge tone={j.statut === "realise" ? "ok" : j.statut === "annule" ? "brand" : j.days_left < 0 ? "err" : "warn"}>{j.statut_label}</Badge>,
              },
              actionsColumn<Jalon>(t("ui.actions"), (j) =>
                j.statut === "a_venir"
                  ? [
                      { label: t("ecarts_m12.contentieux.realiser"), path: `/api/juridique/jalons/${j.id}/realiser/` },
                      { label: t("ecarts_m12.contentieux.annuler"), path: `/api/juridique/jalons/${j.id}/annuler/`, tone: "ghost" as const },
                    ]
                  : [],
              ),
            ]}
          />
        </div>
        <h4>{t("ecarts_m12.contentieux.journal")}</h4>
        <div data-testid="m12-journal">
          <DataTable
            caption={t("ecarts_m12.contentieux.journal")}
            rows={journal.slice(0, 50)}
            density="compact"
            columns={[
              { key: "date", header: t("ecarts_m12.contentieux.date"), render: (a) => formatDate(a.date_action), sortValue: (a) => a.date_action },
              { key: "dossier", header: t("ecarts_m12.contentieux.dossier"), render: (a) => a.contentieux_code },
              { key: "type", header: t("ecarts_m12.contentieux.type"), render: (a) => a.type_label },
              { key: "description", header: t("ecarts_m12.contentieux.description"), render: (a) => a.description },
              { key: "auteur", header: t("tableaux.juridique.auteur"), render: (a) => <span className="muted">{a.auteur_name ?? "—"}</span> },
            ]}
          />
        </div>
      </SectionCard>

      {risques && (
        <SectionCard title={t("ecarts_m12.risk.title")}>
          <p className="muted">
            {t("ecarts_m12.risk.synthese", {
              eleve: risques.par_niveau.eleve, moyen: risques.par_niveau.moyen, faible: risques.par_niveau.faible, nonCote: risques.par_niveau.non_cote,
            })}{" "}
            · {t("ecarts_m12.risk.exposition")} : {fcfa(risques.total_exposition)} · {t("ecarts_m12.risk.engagements", { n: risques.cautions_en_cours })} : {fcfa(risques.engagements_cautions)}
          </p>
          <div data-testid="m12-risk">
            <DataTable
              caption={t("ecarts_m12.risk.title")}
              rows={risques.contentieux}
              columns={[
                { key: "dossier", header: t("ecarts_m12.contentieux.dossier"), render: (r) => `${r.code} · ${r.objet}`, sortValue: (r) => r.code },
                {
                  key: "probabilite",
                  header: t("ecarts_m12.contentieux.probabilite"),
                  sortValue: (r) => r.probabilite_pct,
                  render: (r) => (r.probabilite ? `${t(`ecarts_m12.probas.${r.probabilite}`)} (${r.probabilite_pct} %)` : "—"),
                },
                { key: "enjeu", header: t("ecarts_m12.risk.enjeu"), num: true, render: (r) => fcfa(r.montant_en_jeu), sortValue: (r) => Number(r.montant_en_jeu ?? 0) },
                { key: "exposition", header: t("ecarts_m12.risk.exposition"), num: true, render: (r) => fcfa(r.exposition), sortValue: (r) => Number(r.exposition ?? 0) },
                { key: "niveau", header: t("ecarts_m12.risk.niveau"), render: (r) => <Badge tone={NIVEAU_TONE[r.niveau]}>{t(`ecarts_m12.niveaux.${r.niveau}`)}</Badge> },
              ]}
            />
          </div>
        </SectionCard>
      )}

      <SectionCard title={t("ecarts_m12.dg.title")} subtitle={t("ecarts_m12.dg.note")}>
        <div data-testid="m12-validation-dg">
          <DataTable
            caption={t("ecarts_m12.dg.title")}
            rows={garanties}
            columns={[
              { key: "garantie", header: t("tableaux.juridique.garantie"), render: (g) => `${g.code} · ${g.label}`, sortValue: (g) => g.code },
              { key: "echeance", header: t("tableaux.juridique.echeance"), render: (g) => formatDate(g.date_echeance), sortValue: (g) => g.date_echeance },
              {
                key: "statut",
                header: t("tableaux.juridique.statut"),
                render: (g) => (
                  <>
                    <Badge tone={g.en_attente_dg ? "warn" : "ok"}>{g.en_attente_dg ? t("ecarts_m12.dg.attente") : t("ecarts_m12.dg.validee")}</Badge>{" "}
                    <span className="muted">{g.statut_label}</span>
                  </>
                ),
              },
              actionsColumn<GarantieLigne>(t("ui.actions"), (g) => [
                ...(g.en_attente_dg ? [{ label: t("ecarts_m12.dg.valider"), path: `/api/juridique/${g.kind}/${g.id}/valider-dg/`, confirm: t("ecarts_m12.dg.validerQ") }] : []),
                ...(g.kind === "cautions" && g.statut === "en_cours"
                  ? [
                      { label: t("ecarts_m12.dg.lever"), path: `/api/juridique/cautions/${g.id}/lever/`, tone: "ghost" as const },
                      { label: t("ecarts_m12.dg.appeler"), path: `/api/juridique/cautions/${g.id}/appeler/`, tone: "danger" as const, confirm: t("ecarts_m12.dg.appelerQ") },
                    ]
                  : []),
                ...(g.kind === "assurances" && g.statut !== "resiliee"
                  ? [
                      { label: t("ecarts_m12.dg.renouveler"), path: `/api/juridique/assurances/${g.id}/renouveler/`, tone: "ghost" as const, prompt: { name: "date_echeance", label: t("ecarts_m12.dg.nouvelleEcheance") } },
                      { label: t("ecarts_m12.dg.resilier"), path: `/api/juridique/assurances/${g.id}/resilier/`, tone: "danger" as const, confirm: t("ecarts_m12.dg.resilierQ") },
                    ]
                  : []),
              ]),
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m12.alertes.title")}
        actions={<ActionBar actions={[{ label: t("ecarts_m12.alertes.notifier"), path: "/api/juridique/alertes/notifier/", tone: "ghost" as const }]} />}
      >
        <div data-testid="m12-alertes">
          <DataTable
            caption={t("ecarts_m12.alertes.title")}
            rows={alertesExtra}
            emptyLabel={t("ecarts_m12.alertes.aucune")}
            initialSort={{ id: "echeance", desc: false }}
            columns={[
              { key: "type", header: t("ecarts_m12.contentieux.type"), render: (a) => t(`ecarts_m12.alertes.types.${a.type}`) },
              { key: "objet", header: t("tableaux.juridique.objet"), render: (a) => `${a.code} · ${a.libelle}` },
              {
                key: "echeance",
                header: t("tableaux.juridique.echeance"),
                sortValue: (a) => a.date_echeance,
                render: (a) => (
                  <>
                    {formatDate(a.date_echeance)} <span className="muted">· {a.jours} {t("juridique.jours")}</span>
                  </>
                ),
              },
              {
                key: "bande",
                header: t("tableaux.juridique.urgence"),
                render: (a) => <Badge tone={a.jours < 0 || a.jours <= 15 ? "err" : a.jours <= 60 ? "warn" : "ok"}>{t(`juridique.bande.${a.bande}`)}</Badge>,
              },
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m12.gr.title")}>
        <div data-testid="m12-gr">
          <DataTable
            caption={t("ecarts_m12.gr.title")}
            rows={dossiersGr}
            columns={[
              { key: "dossier", header: t("ecarts_m12.contentieux.dossier"), render: (d) => <span title={d.objet}>{d.code}</span>, sortValue: (d) => d.code },
              {
                key: "mandat",
                header: t("ecarts_m12.gr.mandat"),
                render: (d) => (d.mandat_date_fin ? `${d.mandat_reference || t("ecarts_m12.gr.mandat")} → ${formatDate(d.mandat_date_fin)}` : "—"),
              },
              {
                key: "controle",
                header: t("tableaux.juridique.actualite"),
                render: (d) => (
                  <>
                    <Badge tone={d.controle.a_jour ? "ok" : "warn"}>{d.controle.a_jour ? t("ecarts_m12.gr.aJour") : t("ecarts_m12.gr.pasAJour")}</Badge>{" "}
                    <span className="muted">{d.controle.motifs.join(" ")}</span>
                  </>
                ),
              },
              actionsColumn<DossierGr>(t("ui.actions"), (d) =>
                d.statut !== "cloture"
                  ? [
                      { label: t("ecarts_m12.gr.mandat"), path: `/api/juridique/dossiers-gr/${d.id}/mandat/`, tone: "ghost" as const, prompt: { name: "mandat_date_fin", label: t("ecarts_m12.gr.mandatFin") } },
                      { label: t("ecarts_m12.gr.revoir"), path: `/api/juridique/dossiers-gr/${d.id}/revoir/`, tone: "ghost" as const },
                    ]
                  : [],
              ),
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m12.archivage.title")} subtitle={t("ecarts_m12.archivage.note")}>
        <div data-testid="m12-retention">
          <DataTable
            caption={t("tableaux.juridique.retention")}
            rows={types}
            density="compact"
            columns={[
              { key: "type", header: t("tableaux.juridique.typeDocument"), render: (ty) => ty.label, sortValue: (ty) => ty.label },
              {
                key: "duree",
                header: t("tableaux.juridique.duree"),
                num: true,
                sortValue: (ty) => ty.retention_years,
                render: (ty) => (ty.retention_years === null ? t("ecarts_m12.archivage.sansEcheance") : t("ecarts_m12.archivage.ans", { n: ty.retention_years })),
              },
              {
                key: "statut",
                header: t("tableaux.juridique.statut"),
                render: (ty) => <Badge tone={ty.retention_provisoire ? "warn" : "ok"}>{ty.retention_provisoire ? t("ecarts_m12.provisoire") : t("ecarts_m12.confirme")}</Badge>,
              },
              actionsColumn<TypeDoc>(t("ui.actions"), (ty) => [
                { label: t("ecarts_m12.archivage.modifier"), path: `/api/documents/types/${ty.id}/definir-retention/`, tone: "ghost" as const, prompt: { name: "retention_years", label: t("ecarts_m12.archivage.duree") } },
                ...(ty.retention_provisoire ? [{ label: t("ecarts_m12.parametres.confirmer"), path: `/api/documents/types/${ty.id}/confirmer-retention/`, tone: "ghost" as const }] : []),
              ]),
            ]}
          />
        </div>
        <h4>{t("ecarts_m12.archivage.candidats")}</h4>
        <div data-testid="m12-candidats-purge">
          <DataTable
            caption={t("ecarts_m12.archivage.candidats")}
            rows={candidats}
            emptyLabel={t("ecarts_m12.archivage.aucunCandidat")}
            columns={[
              { key: "document", header: t("tableaux.juridique.document"), render: (c) => c.title },
              { key: "type", header: t("tableaux.juridique.typeDocument"), render: (c) => c.type_label },
              { key: "fin", header: t("tableaux.juridique.finRetention"), render: (c) => formatDate(c.fin_retention), sortValue: (c) => c.fin_retention },
              actionsColumn<Candidat>(t("ui.actions"), (c) => [{ label: t("ecarts_m12.archivage.proposer"), path: "/api/documents/purges/", body: { document: c.id }, tone: "ghost" as const }]),
            ]}
          />
        </div>
        <h4>{t("tableaux.juridique.purges")}</h4>
        <div data-testid="m12-purges">
          <DataTable
            caption={t("tableaux.juridique.purges")}
            rows={purges}
            emptyLabel={t("tableaux.juridique.aucunePurge")}
            columns={[
              { key: "document", header: t("tableaux.juridique.document"), render: (p) => p.document_title },
              { key: "type", header: t("tableaux.juridique.typeDocument"), render: (p) => p.type_label },
              { key: "fin", header: t("tableaux.juridique.finRetention"), render: (p) => formatDate(p.fin_retention), sortValue: (p) => p.fin_retention },
              { key: "statut", header: t("tableaux.juridique.statut"), render: (p) => <Badge tone={p.statut === "executee" ? "ok" : p.statut === "rejetee" ? "brand" : "warn"}>{p.statut_label}</Badge> },
              actionsColumn<Purge>(
                t("ui.actions"),
                (p) =>
                  p.statut === "proposee"
                    ? [
                        { label: t("ecarts_m12.archivage.rejeter"), path: `/api/documents/purges/${p.id}/rejeter/`, tone: "ghost" as const },
                        { label: t("ecarts_m12.archivage.valider"), path: `/api/documents/purges/${p.id}/valider/`, tone: "danger" as const, confirm: t("ecarts_m12.archivage.validerQ") },
                      ]
                    : [],
              ),
            ]}
          />
        </div>
      </SectionCard>
    </div>
  );
}
