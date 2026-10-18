import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CalendarCheck, Coins, Inbox, PieChart, Target } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { GrAffairesSection } from "../components/workflow/GrAffairesSection";
import { MaintenanceCoutsSection } from "../components/workflow/MaintenanceM8Section";
import { SaisieBudgetaireSection } from "../components/workflow/SaisieBudgetaireSection";
import { PilotageGestionSection } from "../components/workflow/PilotageGestionSection";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataTable, EmptyState, ErrorState, Kpi, PageHeader, SearchField, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDate, formatNumber } from "../lib/format";
import { pagedQuery } from "../lib/usePagedList";
import type {
  AnalyseEcart,
  Budget,
  BudgetRevision,
  ClotureGestion,
  MargeRow,
  FiscalYear,
  MargesResult,
  Paginated,
  StatutBudget,
} from "../types";

type BudgetGroups = Record<StatutBudget, Budget[]>;

const BUD_BADGE: Record<StatutBudget, "ok" | "warn" | "err" | "brand"> = {
  brouillon: "warn",
  approuve: "ok",
  cloture: "err",
};
const BUD_ORDER: StatutBudget[] = ["brouillon", "approuve", "cloture"];
const BUD_VALID = new Set<StatutBudget>(BUD_ORDER);

type Visas = { visa_daf_par: string | null; visa_cg_par: string | null };

/** Double visa DAF + CG : l'API exige `visa` dans le corps ; on ne propose que les visas encore manquants. */
function visaPrompt(t: (key: string) => string, v: Visas) {
  const options = [
    ...(v.visa_daf_par ? [] : [{ value: "daf", label: t("controleGestion.visa.daf") }]),
    ...(v.visa_cg_par ? [] : [{ value: "cg", label: t("controleGestion.visa.cg") }]),
  ];
  return { name: "visa", label: t("controleGestion.visa.label"), options };
}

function VisaStatus({ v }: { v: Visas }) {
  const { t } = useTranslation();
  return (
    <div className="meta">
      <Badge tone={v.visa_daf_par ? "ok" : "warn"}>{t(`controleGestion.visa.${v.visa_daf_par ? "dafPose" : "dafAttente"}`)}</Badge>{" "}
      <Badge tone={v.visa_cg_par ? "ok" : "warn"}>{t(`controleGestion.visa.${v.visa_cg_par ? "cgPose" : "cgAttente"}`)}</Badge>
    </div>
  );
}

export function BudgetCard({ b, index }: { b: Budget; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        {b.code} <span className="muted">· {t(`controleGestion.budgetType${b.type_budget === "charge" ? "Charge" : "Produit"}`)}</span>
      </div>
      <div className="meta">{b.label}</div>
      <div className="meta">
        {b.has_amount_access && b.montant !== null
          ? `${formatNumber(b.montant)} F`
          : "••••••"}
        {b.analytic_code ? ` · ${b.axis_code ?? "axe"}:${b.analytic_code}` : ""}
        {b.nb_revisions > 0 ? ` · R${b.nb_revisions}` : ""}
      </div>
      {b.statut === "brouillon" && <VisaStatus v={b} />}
      <ActionBar
        actions={[
          ...(b.statut === "brouillon"
            ? [{ label: t("controleGestion.act.approuver"), path: `/api/controle-gestion/budgets/${b.id}/approuver/`, prompt: visaPrompt(t, b) }]
            : []),
          ...(b.statut === "approuve"
            ? [{ label: t("actions.cloturer"), path: `/api/controle-gestion/budgets/${b.id}/cloturer/`, tone: "ghost" as const, confirm: t("actions.confirmCloturer") }]
            : []),
        ]}
      />
    </BoardCard>
  );
}

type T = (key: string, opts?: Record<string, unknown>) => string;
type MargeLigne = MargeRow & { id: string };

const money = (access: boolean, v: string | number | null) => (access && v !== null ? `${formatNumber(v)} F` : "••••••");

function margeColumns(t: T): Column<MargeLigne>[] {
  return [
    {
      key: "axe",
      header: t("controleGestion.col.axe"),
      render: (r) => (
        <>
          {r.libelle || "—"} <span className="muted">({r.code_axe})</span>
        </>
      ),
    },
    { key: "produits", header: t("controleGestion.produits"), num: true, render: (r) => `${formatNumber(r.produits)} F` },
    { key: "charges", header: t("controleGestion.charges"), num: true, render: (r) => `${formatNumber(r.charges)} F` },
    { key: "marge", header: t("controleGestion.marge"), num: true, render: (r) => `${formatNumber(r.marge)} F` },
    {
      key: "taux",
      header: t("controleGestion.col.taux"),
      num: true,
      render: (r) => (r.taux_marge !== null ? `${formatNumber(r.taux_marge)} %` : "—"),
    },
  ];
}

function clotureColumns(t: T): Column<ClotureGestion>[] {
  return [
    { key: "code", header: t("controleGestion.col.code"), render: (c) => c.code },
    { key: "periode", header: t("controleGestion.col.periode"), render: (c) => c.period_label },
    { key: "date", header: t("controleGestion.col.dateCloture"), render: (c) => (c.date_cloture ? formatDate(c.date_cloture) : "—") },
    {
      key: "delai",
      header: t("controleGestion.col.delai"),
      num: true,
      render: (c) => (c.jours_ecoulement !== null ? `${c.jours_ecoulement} ${t("controleGestion.jours")}` : t("controleGestion.enAttente")),
    },
    {
      key: "reporting",
      header: t("controleGestion.col.reporting"),
      render: (c) => (
        <>
          <Badge tone={c.reporting_statut === "a_temps" ? "ok" : c.reporting_statut === "hors_delai" ? "err" : "warn"}>
            {t(`controleGestion.reporting_statut.${c.reporting_statut}`)}
          </Badge>
          <div className="meta">
            J+4 {formatDate(c.echeance_j4)} · J+6 {formatDate(c.echeance_j6)}
            {c.reporting_provisoire ? ` · ${t("controleGestion.joursProvisoires")}` : ""}
          </div>
        </>
      ),
    },
    {
      key: "statut",
      header: t("controleGestion.col.statut"),
      render: (c) =>
        c.statut === "realisee" ? (
          <>
            <Badge tone={c.conforme_j4 ? "ok" : "err"}>{c.conforme_j4 ? t("controleGestion.conformeJ4") : t("controleGestion.horsJ4")}</Badge>
            {c.date_publication ? (
              <div className="meta">{t("controleGestion.publieLe", { date: formatDate(c.date_publication) })}</div>
            ) : (
              <ActionBar actions={[{ label: t("controleGestion.act.publier"), path: `/api/controle-gestion/clotures/${c.id}/publier/` }]} />
            )}
          </>
        ) : (
          <>
            <Badge tone="warn">{t(`controleGestion.cloture_statut.${c.statut}`)}</Badge>
            <ActionBar actions={[{ label: t("controleGestion.act.realiser"), path: `/api/controle-gestion/clotures/${c.id}/realiser/` }]} />
          </>
        ),
    },
  ];
}

export function revisionColumns(t: T): Column<BudgetRevision>[] {
  return [
    { key: "code", header: t("controleGestion.col.code"), render: (r) => r.code },
    { key: "budget", header: t("controleGestion.col.budget"), render: (r) => `${r.budget_code} · R${r.numero}` },
    { key: "montant", header: t("controleGestion.col.nouveauMontant"), num: true, render: (r) => money(r.has_amount_access, r.nouveau_montant) },
    { key: "auteur", header: t("controleGestion.col.auteur"), render: (r) => r.created_by_name ?? "—" },
    { key: "comment", header: t("controleGestion.col.commentaire"), render: (r) => r.commentaire || "—" },
    {
      key: "statut",
      header: t("controleGestion.col.statut"),
      render: (r) => (
        <>
          <Badge tone={r.statut === "appliquee" ? "ok" : r.statut === "annulee" ? "err" : "warn"}>
            {t(`controleGestion.revision_statut.${r.statut}`)}
          </Badge>
          {r.statut === "brouillon" && (
            <>
              <VisaStatus v={r} />
              <ActionBar
                actions={[{ label: t("controleGestion.act.appliquer"), path: `/api/controle-gestion/revisions/${r.id}/appliquer/`, prompt: visaPrompt(t, r) }]}
              />
            </>
          )}
        </>
      ),
    },
  ];
}

export function ControleGestionPage() {
  const { t } = useTranslation();

  const fy = useQuery({
    queryKey: ["cg-fiscal-years"],
    queryFn: () => api.fiscalYears("?page_size=10"),
    select: (page: Paginated<FiscalYear>): FiscalYear | undefined =>
      [...page.results].sort((a, b) => b.year - a.year)[0],
  });

  const yearParam = fy.data ? `?fiscal_year=${fy.data.id}` : "";

  const [budSearch, setBudSearch] = useState("");
  const budgets = useQuery({
    queryKey: ["cg-budgets", fy.data?.id, budSearch],
    queryFn: () => api.cgBudgets(pagedQuery(1, 500, budSearch)),
    placeholderData: keepPreviousData,
    select: (page: Paginated<Budget>) => {
      const groups: BudgetGroups = { brouillon: [], approuve: [], cloture: [] };
      for (const b of page.results) {
        if (BUD_VALID.has(b.statut)) groups[b.statut].push(b);
      }
      return groups;
    },
    enabled: Boolean(fy.data),
  });

  const revisions = useQuery({
    queryKey: ["cg-revisions"],
    queryFn: () => api.listAll<BudgetRevision>("/api/controle-gestion/revisions/"),
  });

  const clotures = useQuery({
    queryKey: ["cg-clotures", fy.data?.id],
    queryFn: () => api.cgClotures(yearParam),
    select: (page: Paginated<ClotureGestion>) => page.results,
    enabled: Boolean(fy.data),
  });

  const analyses = useQuery({
    queryKey: ["cg-analyses-ecart"],
    queryFn: () => api.listAll<AnalyseEcart>("/api/controle-gestion/analyses-ecart/?statut=a_analyser"),
  });

  const cloturesStats = useQuery({
    queryKey: ["cg-clotures-stats", fy.data?.id],
    queryFn: () => api.cgCloturesStats(yearParam),
    enabled: Boolean(fy.data),
  });

  const marges = useQuery({
    queryKey: ["cg-marges", fy.data?.id],
    queryFn: () => api.cgMarges(yearParam),
    enabled: Boolean(fy.data),
  });

  if (!fy.data || budgets.isLoading || !budgets.data)
    return <BoardSkeleton cols={3} rows={3} />;

  if (budgets.isError || marges.isError || cloturesStats.isError)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void budgets.refetch();
          void revisions.refetch();
          void clotures.refetch();
          void cloturesStats.refetch();
          void marges.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const groups = budgets.data;
  const revs = revisions.data ?? [];
  const closed = clotures.data ?? [];
  const stats = cloturesStats.data;
  const m = marges.data as MargesResult | undefined;
  const enCours = groups["brouillon"].length + groups["approuve"].length;
  const appliquees = revs.filter((r) => r.statut === "appliquee").length;

  return (
    <>
      <PageHeader title={t("controleGestion.title")} />

      <div className="kpi-grid">
        <Kpi label={t("controleGestion.budgets")} value={enCours} hint={t("controleGestion.variance")} icon={PieChart} tone="brand" delay={0} />
        <Kpi label={t("controleGestion.revisions")} value={appliquees} hint="R1 - R4" icon={Target} tone="warn" delay={0.05} />
        <Kpi label={t("controleGestion.clotures")} value={stats ? `${stats.conformes_j4}/${stats.periodes}` : "—"} hint={t("controleGestion.realizeesJ4")} icon={CalendarCheck} tone="brand" delay={0.1} />
        <Kpi label={t("controleGestion.marge")} value={m && m.totals.marge_hors_gr !== null ? `${formatNumber(m.totals.marge_hors_gr)} F` : "••••••"} hint={`${t("controleGestion.coutGr")} ${m ? formatNumber(m.totals.cout_gr) : "—"} F`} icon={Coins} tone="accent" delay={0.15} />
      </div>

      <SearchField value={budSearch} onChange={setBudSearch} placeholder={t("controleGestion.searchBudgets")} />

      <div style={{ overflowX: "auto" }}>
        <Board>
          {BUD_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`controleGestion.statut_budget.${st}`)}
              count={groups[st].length}
              tone={BUD_BADGE[st]}
              delay={ci * 0.05}
              minWidth={280}
              limit={20}
            >
              {groups[st].length === 0 ? (
                <EmptyState icon={Inbox} label={t("common.empty")} />
              ) : (
                groups[st].map((b, i) => <BudgetCard key={b.id} b={b} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      {m && m.rows.length > 0 && (
        <SectionCard title={`${t("controleGestion.marges")} · ${m.rows.length}`}>
          <DataTable
            rows={m.rows.map((r, i) => ({ ...r, id: String(r.analytic ?? `${r.code_axe}-${i}`) }))}
            columns={margeColumns(t)}
            caption={t("controleGestion.marges")}
          />
        </SectionCard>
      )}

      {(analyses.data?.length ?? 0) > 0 && (
        <SectionCard title={`${t("controleGestion.analysesEcart")} · ${analyses.data?.length}`}>
          {analyses.data?.map((a) => (
            <div key={a.id} className="card" style={{ marginBottom: "0.5rem" }}>
              <div className="title">
                {a.code} · {a.budget_code} — {a.period_label}{" "}
                <Badge tone={a.en_retard ? "err" : "warn"}>
                  {Number(a.ecart_pct) > 0 ? "+" : ""}
                  {a.ecart_pct} %
                </Badge>
              </div>
              <div className="meta">
                {a.budget_label} · {t("controleGestion.echeanceAnalyse")} {formatDate(a.echeance)}
                {a.en_retard ? ` · ${t("controleGestion.enRetard")}` : ""}
              </div>
              <ActionBar
                actions={[
                  {
                    label: t("controleGestion.analyser"),
                    path: `/api/controle-gestion/analyses-ecart/${a.id}/analyser/`,
                    prompt: { name: "analyse", label: t("controleGestion.analyseLabel") },
                  },
                ]}
              />
            </div>
          ))}
        </SectionCard>
      )}

      <SaisieBudgetaireSection fiscalYear={fy.data.id} budgets={[...groups.brouillon, ...groups.approuve, ...groups.cloture]} />
      <PilotageGestionSection fiscalYear={fy.data?.id} />
      <GrAffairesSection fiscalYear={fy.data?.id} />
      <MaintenanceCoutsSection />

      {closed.length > 0 && (
        <SectionCard title={`${t("controleGestion.clotures")} · ${closed.length}`}>
          <DataTable rows={closed} columns={clotureColumns(t)} caption={t("controleGestion.clotures")} />
        </SectionCard>
      )}

      {revs.length > 0 && (
        <SectionCard title={`${t("controleGestion.revisions")} · ${revs.length}`}>
          <DataTable rows={revs} columns={revisionColumns(t)} caption={t("controleGestion.revisions")} />
        </SectionCard>
      )}

      <p className="muted" style={{ marginTop: "0.5rem" }}>
        {t("controleGestion.pendingNote")}
      </p>
    </>
  );
}