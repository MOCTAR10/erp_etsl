import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { FileText, Gavel, Scale, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import "../styles/pages/sections.css";
import { refLabel, sansPrefixeType } from "../components/sections/affichage";
import { api } from "../api/client";
import { EcartsM12Section } from "../components/juridique/EcartsM12Section";
import { DocumentsOfficielsSection, RechercheJuridiqueSection } from "../components/workflow/JuridiqueM12Section";
import { Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataTable, ErrorState, Kpi, PageHeader, PagedDataGrid, QuickForm, SearchField, SectionCard, SectionNav } from "../components/ui";
import type { Column } from "../components/ui";
import { actionsColumn } from "../components/ui/DataTable";
import { formatDate, formatMoney } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import type {
  AlerteEcheance,
  AlertesResult,
  Assurance,
  BandeEcheance,
  Caution,
  Contentieux,
  Convention,
  Courrier,
  DossierGlobalRental,
  JuridiqueStats,
  Paginated,
  Reunion,
  StatutAssurance,
  StatutCaution,
  StatutContentieux,
  StatutConvention,
  StatutCourrier,
  StatutDossierGR,
  StatutReunion,
} from "../types";

const BANDE_BADGE: Record<BandeEcheance, "ok" | "warn" | "err"> = {
  j90: "ok",
  j60: "warn",
  j30: "warn",
  j15: "err",
  j0: "err",
  expiree: "err",
};
const BANDES: BandeEcheance[] = ["expiree", "j0", "j15", "j30", "j60", "j90"];
/** Alertes affichées d'emblée (les plus urgentes) ; la liste complète reste à un clic. */
const ALERTES_VISIBLES = 8;

/** Alertes d'échéance (conventions, cautions, assurances), de la plus urgente à la plus lointaine. */
function alerteColumns(t: T): Column<AlerteEcheance & { id: string }>[] {
  return [
    { key: "type", header: t("tableaux.entetes.colType"), render: (el) => t(`juridique.${el.type}`) },
    {
      key: "libelle",
      header: t("tableaux.entetes.colLibelle"),
      sortValue: (el) => el.libelle,
      render: (el) => (
        <>
          {el.libelle}
          <br />
          <span className="muted">{el.code}</span>
        </>
      ),
    },
    { key: "echeance", header: t("tableaux.entetes.colEcheance"), sortValue: (el) => el.date_echeance, render: (el) => formatDate(el.date_echeance) },
    { key: "jours", header: t("tableaux.entetes.colRestant"), num: true, sortValue: (el) => el.jours, render: (el) => `${el.jours} ${t("juridique.jours")}` },
    {
      key: "bande",
      header: t("tableaux.entetes.colBande"),
      render: (el) => <Badge tone={BANDE_BADGE[el.bande]}>{t(`juridique.bande.${el.bande}`)}</Badge>,
    },
  ];
}


/** Pastille de colonne par statut de convention (une couleur = un sens ; clôturé/résilié = neutre). */
const CONVENTION_COL_TONE: Record<StatutConvention, "ok" | "warn" | "brand" | "neutral"> = {
  signe: "ok",
  en_signature: "brand",
  brouillon: "warn",
  cloture: "neutral",
  resilie: "neutral",
};

function ConventionCard({ c, index }: { c: Convention; index: number }) {
  const { t } = useTranslation();
  const actif = c.statut === "signe";
  // Échéance : rouge si dépassée sur une convention encore signée, orange si à renouveler, neutre sinon.
  const tone = actif && c.days_left !== null && c.days_left < 0 ? "err" : actif && c.a_renouveler ? "warn" : "neutral";
  const montant = c.has_amount_access && c.montant !== null ? formatMoney(c.montant) : "••••••";
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">
          {c.code} · {refLabel(t, "contrat", c.type, c.type_label)}
        </span>
      </div>
      <div className="title" title={c.titre}>
        {sansPrefixeType(c.titre)}
      </div>
      {c.partenaire_name ? <div className="meta">{c.partenaire_name}</div> : null}
      <div className="card-foot">
        <span>
          {c.date_fin ? (
            <Badge tone={tone}>
              {formatDate(c.date_fin)}
              {actif && c.days_left !== null ? ` · ${c.days_left} ${t("juridique.jours")}` : ""}
            </Badge>
          ) : null}
        </span>
        <span className="amount">{montant}</span>
      </div>
    </BoardCard>
  );
}

type T = (key: string, opts?: Record<string, unknown>) => string;
type Tone = "ok" | "warn" | "err" | "brand";

const CAUTION_TONE: Record<StatutCaution, Tone> = { en_cours: "ok", levee: "brand", appelee: "err", expiree: "err" };
const ASSURANCE_TONE: Record<StatutAssurance, Tone> = { active: "ok", a_renouveler: "warn", expiree: "err", resiliee: "err" };
const CONTENTIEUX_TONE: Record<StatutContentieux, Tone> = {
  ouvert: "warn",
  en_instruction: "brand",
  gagne: "ok",
  perdu: "err",
  transaction: "ok",
  cloture: "brand",
};
const COURRIER_TONE: Record<StatutCourrier, Tone> = { recu: "warn", enregistre: "brand", classe: "ok", archive: "ok" };
const REUNION_TONE: Record<StatutReunion, Tone> = { planifiee: "warn", tenue: "ok", cloturee: "brand" };
const GR_TONE: Record<StatutDossierGR, Tone> = { brouillon: "warn", ouvert: "brand", cloture: "ok" };

const amount = (access: boolean, value: string | number | null) =>
  access && value !== null ? formatMoney(value) : "••••••";
const dateOr = (iso: string | null | undefined) => (iso ? formatDate(iso) : "—");
const daysLeft = (t: T, d: number | null) => (d === null ? "—" : `${d} ${t("juridique.jours")}`);

function cautionColumns(t: T): Column<Caution>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (c) => c.code },
    { key: "type", header: t("juridique.col.type"), render: (c) => refLabel(t, "caution", c.type, c.type_label) },
    { key: "benef", header: t("juridique.col.beneficiaire"), render: (c) => c.beneficiaire || "—" },
    { key: "montant", header: t("juridique.col.montant"), num: true, render: (c) => amount(c.has_amount_access, c.montant) },
    { key: "ech", header: t("juridique.col.echeance"), render: (c) => dateOr(c.date_echeance) },
    { key: "reste", header: t("juridique.col.reste"), num: true, render: (c) => daysLeft(t, c.days_left) },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (c) => <Badge tone={CAUTION_TONE[c.statut]}>{t(`juridique.statut_caution.${c.statut}`)}</Badge>,
    },
  ];
}

function assuranceColumns(t: T): Column<Assurance>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (a) => a.code },
    { key: "type", header: t("juridique.col.type"), render: (a) => refLabel(t, "assurance", a.type, a.type_label) },
    { key: "police", header: t("juridique.col.police"), render: (a) => a.numero_police || "—" },
    { key: "assureur", header: t("juridique.col.assureur"), render: (a) => a.assureur_name ?? "—" },
    { key: "prime", header: t("juridique.col.prime"), num: true, render: (a) => amount(a.has_amount_access, a.prime_annuelle) },
    { key: "ech", header: t("juridique.col.echeance"), render: (a) => dateOr(a.date_echeance) },
    { key: "reste", header: t("juridique.col.reste"), num: true, render: (a) => daysLeft(t, a.days_left) },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (a) => <Badge tone={ASSURANCE_TONE[a.statut]}>{t(`juridique.statut_assurance.${a.statut}`)}</Badge>,
    },
  ];
}

function contentieuxColumns(t: T): Column<Contentieux>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (l) => l.code },
    { key: "objet", header: t("juridique.col.objet"), render: (l) => l.objet },
    { key: "partie", header: t("juridique.col.partieAdverse"), render: (l) => l.partie_adverse ?? "—" },
    { key: "phase", header: t("juridique.col.phase"), render: (l) => refLabel(t, "phase", l.phase, l.phase_label) },
    { key: "enjeu", header: t("juridique.col.enjeu"), num: true, render: (l) => amount(l.has_amount_access, l.montant_en_jeu) },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (l) => <Badge tone={CONTENTIEUX_TONE[l.statut]}>{t(`juridique.statut_contentieux.${l.statut}`)}</Badge>,
    },
  ];
}

function grColumns(t: T): Column<DossierGlobalRental>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (g) => g.code },
    { key: "objet", header: t("juridique.col.objet"), render: (g) => g.objet },
    { key: "partner", header: t("juridique.col.partenaire"), render: (g) => g.partenaire_gr_name },
    {
      key: "montant",
      header: t("juridique.col.montant"),
      num: true,
      // Le compte 618 est une imputation, pas un statut : en ligne secondaire sous le montant.
      render: (g) => (
        <>
          {amount(g.has_amount_access, g.montant_estime)}
          {g.signe_618 && (
            <span className="cell-sub" title={t("tableaux.logistique.compte618")}>
              {t("premiumModules.compte618")}
            </span>
          )}
        </>
      ),
    },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (g) => <Badge tone={GR_TONE[g.statut]}>{t(`juridique.statut_gr.${g.statut}`)}</Badge>,
    },
  ];
}

function courrierColumns(t: T): Column<Courrier>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (c) => c.code },
    { key: "sens", header: t("juridique.col.sens"), render: (c) => refLabel(t, "sens", c.sens, c.sens_label) },
    { key: "objet", header: t("juridique.col.objet"), render: (c) => c.objet },
    { key: "tiers", header: t("juridique.col.tiers"), render: (c) => c.tiers_name ?? "—" },
    { key: "date", header: t("juridique.col.date"), render: (c) => <span className="r3-nowrap">{dateOr(c.date_reception ?? c.date_courrier)}</span> },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (c) => (
        <>
          <Badge tone={COURRIER_TONE[c.statut]}>{t(`juridique.statut_courrier.${c.statut}`)}</Badge>
        </>
      ),
    },
    actionsColumn<Courrier>(t("ui.actions"), (c) => [
      ...(c.statut === "recu"
        ? [{ label: t("juridique.act.enregistrer"), path: `/api/juridique/courriers/${c.id}/enregistrer/`, tone: "ghost" as const }]
        : []),
      ...(c.statut === "recu" || c.statut === "enregistre"
        ? [{ label: t("juridique.act.classer"), path: `/api/juridique/courriers/${c.id}/classer/`, tone: "ghost" as const }]
        : []),
      ...(c.statut === "enregistre" || c.statut === "classe"
        ? [{ label: t("juridique.act.archiver"), path: `/api/juridique/courriers/${c.id}/archiver/`, tone: "ghost" as const }]
        : []),
    ]),
  ];
}

function reunionColumns(t: T): Column<Reunion>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (r) => r.code },
    { key: "type", header: t("juridique.col.type"), render: (r) => refLabel(t, "reunion", r.type, r.type_label) },
    { key: "objet", header: t("juridique.col.objet"), render: (r) => r.objet },
    { key: "date", header: t("juridique.col.date"), render: (r) => dateOr(r.date_reunion) },
    { key: "decisions", header: t("juridique.col.decisions"), num: true, render: (r) => r.nb_decisions },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (r) => <Badge tone={REUNION_TONE[r.statut]}>{t(`juridique.statut_reunion.${r.statut}`)}</Badge>,
    },
  ];
}

export function JuridiquePage() {
  const { t } = useTranslation();

  const stats = useQuery({
    queryKey: ["juridique-stats"],
    queryFn: () => api.juridiqueStats(),
  });

  const alertes = useQuery({
    queryKey: ["juridique-alertes"],
    queryFn: () => api.alertesJuridique(),
  });

  const courriers = usePagedList<Courrier>("juridique-courriers", (q) => api.courriersJuridique(q));

  const [convSearch, setConvSearch] = useState("");
  const [toutesAlertes, setToutesAlertes] = useState(false);
  const conventions = useQuery({
    queryKey: ["juridique-conventions", convSearch],
    queryFn: () => api.conventionsJuridique(pagedQuery(1, 500, convSearch)),
    placeholderData: keepPreviousData,
    select: (page: Paginated<Convention>) => page.results,
  });

  const cautions = usePagedList<Caution>("juridique-cautions", (q) => api.cautionsJuridique(q));

  const assurances = usePagedList<Assurance>("juridique-assurances", (q) => api.assurancesJuridique(q));

  const contentieux = usePagedList<Contentieux>("juridique-contentieux", (q) => api.contentieuxJuridique(q));

  const reunions = usePagedList<Reunion>("juridique-reunions", (q) => api.reunionsJuridique(q));

  const dossiersGr = usePagedList<DossierGlobalRental>("juridique-dossiers-gr", (q) => api.dossiersGrJuridique(q));

  const loading =
    !stats.data || alertes.isLoading || conventions.isLoading || cautions.query.isLoading || assurances.query.isLoading;

  if (loading) return <BoardSkeleton cols={4} rows={3} />;

  if (alertes.isError || conventions.isError)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void stats.refetch();
          void alertes.refetch();
          void courriers.query.refetch();
          void conventions.refetch();
          void cautions.query.refetch();
          void assurances.query.refetch();
          void contentieux.query.refetch();
          void reunions.query.refetch();
          void dossiersGr.query.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const s = stats.data as JuridiqueStats;
  const a = alertes.data as AlertesResult;
  const convs = conventions.data ?? [];

  return (
    <>
      <PageHeader
        title={t("juridique.title")}
        subtitle={t("tableaux.entetes.juridique")}
        actions={
          <QuickForm
            title={t("juridique.form.title")}
            endpoint="/api/juridique/courriers/"
            fields={[
              {
                name: "sens",
                label: t("juridique.col.sens"),
                type: "select",
                required: true,
                defaultValue: "entrant",
                options: [
                  { value: "entrant", label: t("juridique.form.entrant") },
                  { value: "sortant", label: t("juridique.form.sortant") },
                ],
              },
              {
                name: "type",
                label: t("juridique.col.type"),
                type: "select",
                required: true,
                defaultValue: "lettre",
                options: ["lettre", "email", "note", "convocation", "proces", "autre"].map((v) => ({ value: v, label: t(`juridique.form.types.${v}`) })),
              },
              { name: "objet", label: t("juridique.col.objet"), required: true },
              { name: "reference", label: t("juridique.form.reference") },
              { name: "expediteur", label: t("juridique.form.expediteur") },
              { name: "destinataire", label: t("juridique.form.destinataire") },
              { name: "date_courrier", label: t("juridique.form.dateCourrier"), type: "date" },
            ]}
          />
        }
      />
      <SectionNav
        items={[
          ...(a.total > 0 ? [{ id: "jur-alertes", label: t("premiumVague2.sections.juridique.alertes") }] : []),
          ...(convs.length > 0 || convSearch ? [{ id: "jur-conventions", label: t("premiumVague2.sections.juridique.conventions") }] : []),
          { id: "jur-garanties", label: t("premiumVague2.sections.juridique.garanties") },
          { id: "jur-contentieux", label: t("premiumVague2.sections.juridique.contentieux") },
          { id: "jur-documents", label: t("premiumVague2.sections.juridique.documents") },
          { id: "jur-suivi", label: t("premiumVague2.sections.juridique.suivi") },
          { id: "jur-parametres", label: t("premiumVague2.sections.juridique.parametres") },
        ]}
      />

      <div className="kpi-grid">
        <Kpi
          label={t("juridique.alertes")}
          value={a.total}
          hint={t("revueR3.juridique.alertesHint", {
            expirees: a.compteurs["expiree"] ?? 0,
            urgentes: (a.compteurs["j0"] ?? 0) + (a.compteurs["j15"] ?? 0),
          })}
          icon={Scale}
          tone="warn"
          delay={0}
        />
        <Kpi label={t("juridique.conventions")} value={s.conventions} hint={t("tableaux.entetes.aRenouveler", { n: s.conventions_a_renouveler })} icon={FileText} tone="brand" delay={0.05} />
        <Kpi label={t("juridique.contentieux")} value={s.contentieux_ouverts} hint={t("tableaux.entetes.courriers", { n: s.courriers })} icon={Gavel} tone="err" delay={0.1} />
        <Kpi label={t("juridique.cautions")} value={s.cautions_en_cours} hint={t("tableaux.entetes.assurances", { n: s.assurances })} icon={ShieldCheck} tone="brand" delay={0.15} />
      </div>

      {a.total > 0 ? (
        <div id="jur-alertes" className="page-section">
          <SectionCard
            title={`${t("juridique.alertes")} · ${a.total}`}
            subtitle={t("revueR3.juridique.alertesSub")}
            actions={
              a.total > ALERTES_VISIBLES ? (
                <button type="button" className="btn ghost sm" onClick={() => setToutesAlertes((v) => !v)} aria-expanded={toutesAlertes}>
                  {toutesAlertes ? t("revueR3.cg.reduire") : t("revueR3.juridique.toutVoir", { count: a.total })}
                </button>
              ) : null
            }
          >
            <DataTable
              rows={BANDES.flatMap((bande) =>
                [...a.conventions, ...a.cautions, ...a.assurances]
                  .filter((el) => el.bande === bande)
                  .map((el) => ({ ...el, id: `${el.type}-${el.code}` })),
              ).slice(0, toutesAlertes ? undefined : ALERTES_VISIBLES)}
              columns={alerteColumns(t)}
              caption={t("juridique.alertes")}
              density="compact"
            />
          </SectionCard>
        </div>
      ) : null}

      {convs.length > 0 || convSearch ? (
        <div id="jur-conventions" className="page-section">
          <h3 className="section-heading">
            {t("revueR3.juridique.conventions")} · {convs.length}
          </h3>
          <SearchField value={convSearch} onChange={setConvSearch} placeholder={t("juridique.searchConventions")} />
          <div>
            <Board label={t("revueR3.juridique.conventions")}>
              {(["signe", "en_signature", "brouillon", "cloture", "resilie"] as StatutConvention[]).map((st, ci) => {
                const items = convs.filter((c) => c.statut === st);
                if (items.length === 0) return null;
                return (
                  <BoardColumn
                    key={st}
                    title={t(`juridique.statut_convention.${st}`)}
                    count={items.length}
                    tone={CONVENTION_COL_TONE[st]}
                    delay={ci * 0.05}
                    limit={6}
                  >
                    {items.map((c, i) => (
                      <ConventionCard key={c.id} c={c} index={i} />
                    ))}
                  </BoardColumn>
                );
              })}
            </Board>
          </div>
        </div>
      ) : null}

      <div id="jur-garanties" className="page-section">
      {(cautions.count > 0 || cautions.search) && (
        <SectionCard title={`${t("juridique.cautions")} · ${cautions.count}`}>
          <PagedDataGrid list={cautions} columns={cautionColumns(t)} caption={t("juridique.cautions")} searchPlaceholder={t("juridique.searchCautions")} />
        </SectionCard>
      )}
      {(assurances.count > 0 || assurances.search) && (
        <SectionCard title={`${t("juridique.assurances")} · ${assurances.count}`}>
          <PagedDataGrid list={assurances} columns={assuranceColumns(t)} caption={t("juridique.assurances")} searchPlaceholder={t("juridique.searchAssurances")} />
        </SectionCard>
      )}
      </div>
      <div id="jur-contentieux" className="page-section">
      {(contentieux.count > 0 || contentieux.search) && (
        <SectionCard title={`${t("juridique.contentieux")} · ${contentieux.count}`}>
          <PagedDataGrid list={contentieux} columns={contentieuxColumns(t)} caption={t("juridique.contentieux")} searchPlaceholder={t("juridique.searchContentieux")} />
        </SectionCard>
      )}
      {(dossiersGr.count > 0 || dossiersGr.search) && (
        <SectionCard title={`GLOBAL RENTAL · ${dossiersGr.count}`}>
          <PagedDataGrid list={dossiersGr} columns={grColumns(t)} caption="GLOBAL RENTAL" searchPlaceholder={t("juridique.searchGr")} />
        </SectionCard>
      )}
      </div>
      <div id="jur-documents" className="page-section">
      <RechercheJuridiqueSection />
      <DocumentsOfficielsSection />
      {(courriers.count > 0 || courriers.search) && (
        <SectionCard title={`${t("juridique.courriers")} · ${courriers.count}`}>
          <PagedDataGrid list={courriers} columns={courrierColumns(t)} caption={t("juridique.courriers")} searchPlaceholder={t("juridique.searchCourriers")} />
        </SectionCard>
      )}
      {(reunions.count > 0 || reunions.search) && (
        <SectionCard title={`${t("juridique.reunions")} · ${reunions.count}`}>
          <PagedDataGrid list={reunions} columns={reunionColumns(t)} caption={t("juridique.reunions")} searchPlaceholder={t("juridique.searchReunions")} />
        </SectionCard>
      )}
      </div>

      <EcartsM12Section />
    </>
  );
}