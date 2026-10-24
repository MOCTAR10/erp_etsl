import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CalendarCheck, Coins, PieChart, Target } from "lucide-react";
import { useTranslation } from "react-i18next";

import "../styles/pages/sections.css";
import { api } from "../api/client";
import i18n from "../i18n";
import { GrAffairesSection } from "../components/workflow/GrAffairesSection";
import { MaintenanceCoutsSection } from "../components/workflow/MaintenanceM8Section";
import { CoutsHseSection } from "../components/hse/HsePermisSection";
import { SaisieBudgetaireSection } from "../components/workflow/SaisieBudgetaireSection";
import { PilotageGestionSection } from "../components/workflow/PilotageGestionSection";
import { EcartsM11Section } from "../components/controleGestion/EcartsM11Section";
import { BalanceAgeeGestionSection, MargesTerminaisonSection } from "../components/suivi/SuiviSections";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataGrid, DataTable, ErrorState, Kpi, PageHeader, SearchField, SectionCard, SectionNav } from "../components/ui";
import type { Column } from "../components/ui";
import { actionsColumn } from "../components/ui/DataTable";
import { formatDate, formatMoney, formatNumber } from "../lib/format";
import { nomPersonne } from "../components/sections/affichage";
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

const BUD_BADGE: Record<StatutBudget, "ok" | "warn" | "neutral"> = {
  brouillon: "warn",
  approuve: "ok",
  cloture: "neutral",
};
const BUD_ORDER: StatutBudget[] = ["brouillon", "approuve", "cloture"];
const BUD_VALID = new Set<StatutBudget>(BUD_ORDER);
const ECARTS_VISIBLES = 8;

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
      <div className="card-top">
        <span className="card-code">
          {b.code} · {t(`controleGestion.budgetType${b.type_budget === "charge" ? "Charge" : "Produit"}`)}
        </span>
      </div>
      <div className="title">{b.label}</div>
      <div className="card-foot">
        <span>
          {b.analytic_code ?? ""}
          {b.nb_revisions > 0 ? `${b.analytic_code ? " · " : ""}${t("revueR3.cg.revisions", { count: b.nb_revisions })}` : ""}
        </span>
        <span className="amount">{b.has_amount_access && b.montant !== null ? formatMoney(b.montant) : "••••••"}</span>
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

/** « 2026-07 » → « juil. 2026 » ; tout autre libellé de période est rendu tel quel. */
function periodeLisible(p: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(p);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, 1).toLocaleDateString(i18n.language, { month: "short", year: "numeric" }) : p;
}
type MargeLigne = MargeRow & { id: string };

const money = (access: boolean, v: string | number | null) => (access && v !== null ? formatMoney(v) : "••••••");

function margeColumns(t: T): Column<MargeLigne>[] {
  return [
    {
      key: "axe",
      header: t("controleGestion.col.axe"),
      render: (r) => r.libelle || <span className="muted">{t("revueR3.cg.nonAffecte")}</span>,
    },
    { key: "produits", header: t("controleGestion.produits"), num: true, render: (r) => formatMoney(r.produits) },
    { key: "charges", header: t("controleGestion.charges"), num: true, render: (r) => formatMoney(r.charges) },
    { key: "marge", header: t("controleGestion.marge"), num: true, render: (r) => formatMoney(r.marge) },
    {
      key: "taux",
      header: t("controleGestion.col.taux"),
      num: true,
      // Le serveur renvoie un ratio (0,13) : affiché en pourcentage à une décimale (« 13,5 % »).
      render: (r) => (r.taux_marge !== null ? `${formatNumber(Number(r.taux_marge) * 100, { decimals: 1 })} %` : "—"),
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

/** Écarts budgétaires > 10 % en attente d'analyse : une ligne par écart, action « Rendre l'analyse ». */
function analyseColumns(t: T): Column<AnalyseEcart>[] {
  return [
    {
      key: "budget",
      header: t("tableaux.entetes.colBudget"),
      sortValue: (a) => a.code,
      render: (a) => (
        <>
          {a.budget_label}
          <span className="cell-sub">
            {periodeLisible(a.period_label)} · {a.budget_code}
          </span>
        </>
      ),
    },
    {
      key: "ecart",
      header: t("tableaux.entetes.colEcart"),
      num: true,
      sortValue: (a) => Number(a.ecart_pct),
      render: (a) => (
        <Badge tone={a.en_retard ? "err" : "warn"}>
          {Number(a.ecart_pct) > 0 ? "+" : ""}
          {formatNumber(a.ecart_pct, { decimals: 1 })} %
        </Badge>
      ),
    },
    {
      key: "echeance",
      header: t("tableaux.entetes.colEcheance"),
      sortValue: (a) => a.echeance,
      render: (a) => (
        <>
          <span className="r3-nowrap">{formatDate(a.echeance)}</span>
          {a.en_retard ? (
            <>
              {" "}
              <Badge tone="err">{t("tableaux.entetes.enRetard")}</Badge>
            </>
          ) : null}
        </>
      ),
    },
    actionsColumn<AnalyseEcart>(t("ui.actions"), (a) => [
      {
        label: t("controleGestion.analyser"),
        path: `/api/controle-gestion/analyses-ecart/${a.id}/analyser/`,
        prompt: { name: "analyse", label: t("controleGestion.analyseLabel") },
      },
    ]),
  ];
}

export function revisionColumns(t: T): Column<BudgetRevision>[] {
  return [
    { key: "code", header: t("controleGestion.col.code"), render: (r) => r.code },
    { key: "budget", header: t("controleGestion.col.budget"), render: (r) => `${r.budget_code} · R${r.numero}` },
    { key: "montant", header: t("controleGestion.col.nouveauMontant"), num: true, render: (r) => money(r.has_amount_access, r.nouveau_montant) },
    { key: "auteur", header: t("controleGestion.col.auteur"), render: (r) => nomPersonne(t, r.created_by_name) },
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
  const [tousEcarts, setTousEcarts] = useState(false);
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
  // Les écarts les plus forts d'abord (en retard en tête) : la liste complète reste à un clic.
  const ecartsTries = [...(analyses.data ?? [])].sort(
    (x, y) => Number(y.en_retard) - Number(x.en_retard) || Math.abs(Number(y.ecart_pct)) - Math.abs(Number(x.ecart_pct)),
  );

  return (
    <>
      <PageHeader title={t("controleGestion.title")} subtitle={t("tableaux.entetes.controleGestion")} />
      <SectionNav
        items={[
          { id: "cg-budgets", label: t("premiumVague2.sections.controleGestion.budgets") },
          ...((m && m.rows.length > 0) || (analyses.data?.length ?? 0) > 0 ? [{ id: "cg-marges", label: t("premiumVague2.sections.controleGestion.marges") }] : []),
          { id: "cg-pilotage", label: t("premiumVague2.sections.controleGestion.pilotage") },
          { id: "cg-affaires", label: t("premiumVague2.sections.controleGestion.affaires") },
          { id: "cg-couts", label: t("premiumVague2.sections.controleGestion.couts") },
          ...(closed.length > 0 || revs.length > 0 ? [{ id: "cg-historique", label: t("premiumVague2.sections.controleGestion.historique") }] : []),
        ]}
      />

      <div className="kpi-grid">
        <Kpi label={t("controleGestion.budgets")} value={enCours} hint={t("tableaux.entetes.budgetsHint")} icon={PieChart} tone="brand" delay={0} />
        <Kpi label={t("controleGestion.revisions")} value={appliquees} hint={t("tableaux.entetes.revisionsHint")} icon={Target} tone="warn" delay={0.05} />
        <Kpi label={t("controleGestion.clotures")} value={stats ? `${stats.conformes_j4}/${stats.periodes}` : "—"} hint={t("tableaux.entetes.cloturesHint")} icon={CalendarCheck} tone="brand" delay={0.1} />
        <Kpi label={t("tableaux.entetes.margeHorsGr")} value={m && m.totals.marge_hors_gr !== null ? m.totals.marge_hors_gr : "••••••"} kind="money" hint={t("tableaux.entetes.coutGr", { montant: m ? formatMoney(m.totals.cout_gr) : "—" })} icon={Coins} tone="accent" delay={0.15} />
      </div>

      <div id="cg-budgets" className="page-section">
      <h3 className="section-heading">{t("controleGestion.budgets")}</h3>
      <SearchField value={budSearch} onChange={setBudSearch} placeholder={t("controleGestion.searchBudgets")} />

      <Board label={t("controleGestion.budgets")}>
        {BUD_ORDER.map((st, ci) => (
          <BoardColumn
            key={st}
            title={t(`controleGestion.statut_budget.${st}`)}
            count={groups[st].length}
            tone={BUD_BADGE[st]}
            delay={ci * 0.05}
            limit={6}
            summary={
              groups[st].some((b) => b.has_amount_access && b.montant !== null)
                ? formatMoney(groups[st].reduce((n, b) => n + (b.has_amount_access && b.montant !== null ? Number(b.montant) : 0), 0))
                : undefined
            }
          >
            {groups[st].map((b, i) => (
              <BudgetCard key={b.id} b={b} index={i} />
            ))}
          </BoardColumn>
        ))}
      </Board>
      </div>

      <div id="cg-marges" className="page-section">
      {m && m.rows.length > 0 && (
        <SectionCard title={`${t("controleGestion.marges")} · ${m.rows.length}`}>
          <DataGrid
            rows={m.rows.map((r, i) => ({ ...r, id: String(r.analytic ?? `${r.code_axe}-${i}`) }))}
            columns={margeColumns(t)}
            caption={t("controleGestion.marges")}
          />
        </SectionCard>
      )}

      {(analyses.data?.length ?? 0) > 0 && (
        <SectionCard
          title={`${t("controleGestion.analysesEcart")} · ${analyses.data?.length}`}
          subtitle={t("revueR3.cg.analysesSub")}
          actions={
            (analyses.data?.length ?? 0) > ECARTS_VISIBLES ? (
              <button type="button" className="btn ghost sm" onClick={() => setTousEcarts((v) => !v)} aria-expanded={tousEcarts}>
                {tousEcarts ? t("revueR3.cg.reduire") : t("revueR3.cg.toutVoir", { count: analyses.data?.length ?? 0 })}
              </button>
            ) : null
          }
        >
          <DataTable
            rows={ecartsTries.slice(0, tousEcarts ? undefined : ECARTS_VISIBLES)}
            columns={analyseColumns(t)}
            caption={t("controleGestion.analysesEcart")}
          />
        </SectionCard>
      )}

      </div>

      <div id="cg-pilotage" className="page-section">
        <SaisieBudgetaireSection fiscalYear={fy.data.id} budgets={[...groups.brouillon, ...groups.approuve, ...groups.cloture]} />
        <PilotageGestionSection fiscalYear={fy.data?.id} />
        <EcartsM11Section fiscalYear={fy.data.id} />
      </div>
      <div id="cg-affaires" className="page-section">
        <MargesTerminaisonSection />
        <BalanceAgeeGestionSection />
        <GrAffairesSection fiscalYear={fy.data?.id} />
      </div>
      <div id="cg-couts" className="page-section">
        <MaintenanceCoutsSection />
        <CoutsHseSection />
      </div>

      <div id="cg-historique" className="page-section">
      {closed.length > 0 && (
        <SectionCard title={`${t("controleGestion.clotures")} · ${closed.length}`}>
          <DataGrid rows={closed} columns={clotureColumns(t)} caption={t("controleGestion.clotures")} />
        </SectionCard>
      )}

      {revs.length > 0 && (
        <SectionCard title={`${t("controleGestion.revisions")} · ${revs.length}`}>
          <DataGrid rows={revs} columns={revisionColumns(t)} caption={t("controleGestion.revisions")} />
        </SectionCard>
      )}
      </div>

    </>
  );
}