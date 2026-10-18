import { useQuery } from "@tanstack/react-query";
import { FileText, Gavel, Scale, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { DocumentsOfficielsSection, RechercheJuridiqueSection } from "../components/workflow/JuridiqueM12Section";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataTable, ErrorState, Kpi, PageHeader, QuickForm, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDate, formatNumber } from "../lib/format";
import type {
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

function ConventionCard({ c, index }: { c: Convention; index: number }) {
  const { t } = useTranslation();
  const badge =
    c.statut === "signe"
      ? c.a_renouveler
        ? "warn"
        : "ok"
      : c.statut === "cloture" || c.statut === "resilie"
        ? "err"
        : "warn";
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        {c.code} <span className="muted">· {c.type_label}</span>
      </div>
      <div className="meta">{c.titre}</div>
      <div className="meta">
        {c.has_amount_access && c.montant !== null ? `${formatNumber(c.montant)} F` : "••••••"} ·{" "}
        {c.partenaire_name ?? "—"}
      </div>
      <div className="meta">
        <span className={`badge ${badge}`}>{t(`juridique.statut_convention.${c.statut}`)}</span>{" "}
        {c.date_fin ? (
          <span className="muted">
            {c.date_fin ? formatDate(c.date_fin) : "—"} · {c.days_left !== null ? `${c.days_left} ${t("juridique.jours")}` : "—"}
          </span>
        ) : null}
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
  access && value !== null ? `${formatNumber(value)} F` : "••••••";
const dateOr = (iso: string | null | undefined) => (iso ? formatDate(iso) : "—");
const daysLeft = (t: T, d: number | null) => (d === null ? "—" : `${d} ${t("juridique.jours")}`);

function cautionColumns(t: T): Column<Caution>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (c) => c.code },
    { key: "type", header: t("juridique.col.type"), render: (c) => c.type_label },
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
    { key: "type", header: t("juridique.col.type"), render: (a) => a.type_label },
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
    { key: "phase", header: t("juridique.col.phase"), render: (l) => l.phase_label },
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
    { key: "montant", header: t("juridique.col.montant"), num: true, render: (g) => amount(g.has_amount_access, g.montant_estime) },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (g) => (
        <>
          <Badge tone={GR_TONE[g.statut]}>{t(`juridique.statut_gr.${g.statut}`)}</Badge>{" "}
          {g.signe_618 && <Badge tone="warn">618</Badge>}
        </>
      ),
    },
  ];
}

function courrierColumns(t: T): Column<Courrier>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (c) => c.code },
    { key: "sens", header: t("juridique.col.sens"), render: (c) => c.sens_label },
    { key: "objet", header: t("juridique.col.objet"), render: (c) => c.objet },
    { key: "tiers", header: t("juridique.col.tiers"), render: (c) => c.tiers_name ?? "—" },
    { key: "date", header: t("juridique.col.date"), render: (c) => dateOr(c.date_reception ?? c.date_courrier) },
    {
      key: "statut",
      header: t("juridique.col.statut"),
      render: (c) => (
        <>
          <Badge tone={COURRIER_TONE[c.statut]}>{t(`juridique.statut_courrier.${c.statut}`)}</Badge>
          <ActionBar
            actions={[
              ...(c.statut === "recu"
                ? [{ label: t("juridique.act.enregistrer"), path: `/api/juridique/courriers/${c.id}/enregistrer/`, tone: "ghost" as const }]
                : []),
              ...(c.statut === "recu" || c.statut === "enregistre"
                ? [{ label: t("juridique.act.classer"), path: `/api/juridique/courriers/${c.id}/classer/`, tone: "ghost" as const }]
                : []),
              ...(c.statut === "enregistre" || c.statut === "classe"
                ? [{ label: t("juridique.act.archiver"), path: `/api/juridique/courriers/${c.id}/archiver/` }]
                : []),
            ]}
          />
        </>
      ),
    },
  ];
}

function reunionColumns(t: T): Column<Reunion>[] {
  return [
    { key: "code", header: t("juridique.col.code"), render: (r) => r.code },
    { key: "type", header: t("juridique.col.type"), render: (r) => r.type_label },
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

  const courriers = useQuery({
    queryKey: ["juridique-courriers"],
    queryFn: () => api.courriersJuridique("?page_size=50"),
    select: (page: Paginated<Courrier>) => page.results,
  });

  const conventions = useQuery({
    queryKey: ["juridique-conventions"],
    queryFn: () => api.conventionsJuridique("?page_size=100"),
    select: (page: Paginated<Convention>) => page.results,
  });

  const cautions = useQuery({
    queryKey: ["juridique-cautions"],
    queryFn: () => api.cautionsJuridique("?page_size=50"),
    select: (page: Paginated<Caution>) => page.results,
  });

  const assurances = useQuery({
    queryKey: ["juridique-assurances"],
    queryFn: () => api.assurancesJuridique("?page_size=50"),
    select: (page: Paginated<Assurance>) => page.results,
  });

  const contentieux = useQuery({
    queryKey: ["juridique-contentieux"],
    queryFn: () => api.contentieuxJuridique("?page_size=50"),
    select: (page: Paginated<Contentieux>) => page.results,
  });

  const reunions = useQuery({
    queryKey: ["juridique-reunions"],
    queryFn: () => api.reunionsJuridique("?page_size=50"),
    select: (page: Paginated<Reunion>) => page.results,
  });

  const dossiersGr = useQuery({
    queryKey: ["juridique-dossiers-gr"],
    queryFn: () => api.dossiersGrJuridique("?page_size=50"),
    select: (page: Paginated<DossierGlobalRental>) => page.results,
  });

  const loading =
    !stats.data || alertes.isLoading || conventions.isLoading || cautions.isLoading || assurances.isLoading;

  if (loading) return <BoardSkeleton cols={4} rows={3} />;

  if (alertes.isError || conventions.isError)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void stats.refetch();
          void alertes.refetch();
          void courriers.refetch();
          void conventions.refetch();
          void cautions.refetch();
          void assurances.refetch();
          void contentieux.refetch();
          void reunions.refetch();
          void dossiersGr.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const s = stats.data as JuridiqueStats;
  const a = alertes.data as AlertesResult;
  const convs = conventions.data ?? [];
  const cautionsList = cautions.data ?? [];
  const assurancesList = assurances.data ?? [];
  const courts = courriers.data ?? [];
  const litiges = contentieux.data ?? [];
  const reunionsList = reunions.data ?? [];
  const grs = dossiersGr.data ?? [];

  return (
    <>
      <PageHeader title={t("juridique.title")} />
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

      <div className="kpi-grid">
        <Kpi
          label={t("juridique.alertes")}
          value={a.total}
          hint={
            <>
              <span className="badge err">{a.compteurs["expiree"]}</span> {t("juridique.echeanceExpi")}
              {" · "}
              <span className="badge err">{(a.compteurs["j0"] ?? 0) + (a.compteurs["j15"] ?? 0)}</span> {t("juridique.echeanceJ15")}
              {" · "}
              <span className="badge warn">{a.compteurs["j30"]}</span> {t("juridique.echeanceJ30")}
              {" · "}
              <span className="badge warn">{a.compteurs["j60"]}</span> {t("juridique.echeanceJ60")}
              {" · "}
              <span className="badge ok">{a.compteurs["j90"]}</span> {t("juridique.echeanceJ90")}
            </>
          }
          icon={Scale}
          tone="warn"
          delay={0}
        />
        <Kpi label={t("juridique.conventions")} value={s.conventions} hint={`${t("juridique.conventionsARenouveler")} ${s.conventions_a_renouveler}`} icon={FileText} tone="brand" delay={0.05} />
        <Kpi label={t("juridique.contentieux")} value={s.contentieux_ouverts} hint={`${t("juridique.courriers")} ${s.courriers}`} icon={Gavel} tone="err" delay={0.1} />
        <Kpi label={t("juridique.cautions")} value={s.cautions_en_cours} hint={`${t("juridique.assurances")} ${s.assurances}`} icon={ShieldCheck} tone="brand" delay={0.15} />
      </div>

      {a.total > 0 ? (
        <>
          <h3 className="section-heading">
            {t("juridique.alertes")} · {a.total}
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "0.5rem" }}>
            {BANDES.flatMap((bande) =>
              [...a.conventions, ...a.cautions, ...a.assurances]
                .filter((el) => el.bande === bande)
                .map((el) => (
                  <div className="card kpi" key={`${el.type}-${el.code}`}>
                    <span className="kpi-label">
                      {t(`juridique.${el.type}`)} · {el.code}{" "}
                      <span className={`badge ${BANDE_BADGE[bande]}`}>{t(`juridique.bande.${bande}`)}</span>
                    </span>
                    <span className="kpi-value">{el.libelle}</span>
                    <span className="meta muted">
                      {formatDate(el.date_echeance)} · {el.jours} {t("juridique.jours")}
                    </span>
                  </div>
                ))
            )}
          </div>
        </>
      ) : null}

      {convs.length > 0 ? (
        <>
          <h3 className="section-heading">
            {t("juridique.conventions")} · {convs.length}
          </h3>
          <div style={{ overflowX: "auto" }}>
            <Board>
              {(["signe", "en_signature", "brouillon", "cloture", "resilie"] as StatutConvention[]).map((st, ci) => {
                const items = convs.filter((c) => c.statut === st);
                if (items.length === 0) return null;
                return (
                  <BoardColumn
                    key={st}
                    title={t(`juridique.statut_convention.${st}`)}
                    count={items.length}
                    tone="warn"
                    delay={ci * 0.05}
                    minWidth={280}
                  >
                    {items.map((c, i) => (
                      <ConventionCard key={c.id} c={c} index={i} />
                    ))}
                  </BoardColumn>
                );
              })}
            </Board>
          </div>
        </>
      ) : null}

      {cautionsList.length > 0 && (
        <SectionCard title={`${t("juridique.cautions")} · ${cautionsList.length}`}>
          <DataTable rows={cautionsList} columns={cautionColumns(t)} caption={t("juridique.cautions")} />
        </SectionCard>
      )}
      {assurancesList.length > 0 && (
        <SectionCard title={`${t("juridique.assurances")} · ${assurancesList.length}`}>
          <DataTable rows={assurancesList} columns={assuranceColumns(t)} caption={t("juridique.assurances")} />
        </SectionCard>
      )}
      {litiges.length > 0 && (
        <SectionCard title={`${t("juridique.contentieux")} · ${litiges.length}`}>
          <DataTable rows={litiges} columns={contentieuxColumns(t)} caption={t("juridique.contentieux")} />
        </SectionCard>
      )}
      {grs.length > 0 && (
        <SectionCard title={`GLOBAL RENTAL · ${grs.length}`}>
          <DataTable rows={grs} columns={grColumns(t)} caption="GLOBAL RENTAL" />
        </SectionCard>
      )}
      <RechercheJuridiqueSection />
      <DocumentsOfficielsSection />

      {courts.length > 0 && (
        <SectionCard title={`${t("juridique.courriers")} · ${courts.length}`}>
          <DataTable rows={courts} columns={courrierColumns(t)} caption={t("juridique.courriers")} />
        </SectionCard>
      )}
      {reunionsList.length > 0 && (
        <SectionCard title={`${t("juridique.reunions")} · ${reunionsList.length}`}>
          <DataTable rows={reunionsList} columns={reunionColumns(t)} caption={t("juridique.reunions")} />
        </SectionCard>
      )}
    </>
  );
}