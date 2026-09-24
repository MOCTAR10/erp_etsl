import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Coins, Inbox, PieChart, Target } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Board, BoardCard, BoardColumn, BoardSkeleton, EmptyState, ErrorState, Kpi, PageHeader } from "../components/ui";
import { formatNumber } from "../lib/format";
import type {
  Budget,
  BudgetRevision,
  ClotureGestion,
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

function BudgetCard({ b, index }: { b: Budget; index: number }) {
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
    </BoardCard>
  );
}

function RevisionCard({ r }: { r: BudgetRevision }) {
  const { t } = useTranslation();
  const badge = r.statut === "appliquee" ? "ok" : r.statut === "annulee" ? "err" : "warn";
  return (
    <div className="card kpi" key={r.id}>
      <span className="kpi-label">
        {r.code} · R{r.numero} · {r.budget_code}{" "}
        <span className={`badge ${badge}`}>{t(`controleGestion.revision_statut.${r.statut}`)}</span>
      </span>
      <span className="kpi-value">
        {r.has_amount_access && r.nouveau_montant !== null ? formatNumber(r.nouveau_montant) : "••••••"} F
      </span>
      <span className="meta muted">
        {r.created_by_name ?? "—"} · {r.commentaire || "—"}
      </span>
    </div>
  );
}

function ClotureCard({ c }: { c: ClotureGestion }) {
  const { t } = useTranslation();
  const badge = c.statut === "realisee" ? (c.conforme_j4 ? "ok" : "err") : "warn";
  return (
    <div className="card kpi" key={c.id}>
      <span className="kpi-label">
        {c.code} · {c.period_label}{" "}
        <span className={`badge ${badge}`}>
          {c.statut === "realisee"
            ? c.conforme_j4
              ? t("controleGestion.conformeJ4")
              : t("controleGestion.horsJ4")
            : t(`controleGestion.cloture_statut.${c.statut}`)}
        </span>
      </span>
      <span className="kpi-value">
        {c.jours_ecoulement !== null ? `${c.jours_ecoulement} ${t("controleGestion.jours")}` : t("controleGestion.enAttente")}
      </span>
      <span className="meta muted">{c.date_cloture ?? "—"}</span>
    </div>
  );
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

  const budgets = useQuery({
    queryKey: ["cg-budgets", fy.data?.id],
    queryFn: () => api.cgBudgets("?page_size=100"),
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
    queryFn: () => api.cgRevisions("?page_size=50"),
    select: (page: Paginated<BudgetRevision>) => page.results,
  });

  const clotures = useQuery({
    queryKey: ["cg-clotures", fy.data?.id],
    queryFn: () => api.cgClotures(yearParam),
    select: (page: Paginated<ClotureGestion>) => page.results,
    enabled: Boolean(fy.data),
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

      {m && m.rows.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("controleGestion.marges")} · {m.rows.length}
          </h3>
          <table className="table">
            <thead>
              <tr>
                <th>{t("controleGestion.produits")}</th>
                <th>{t("controleGestion.charges")}</th>
                <th>{t("controleGestion.marge")}</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {m.rows.map((r) => (
                <tr key={r.analytic ?? r.libelle}>
                  <td>{r.libelle || "—"} <span className="muted">({r.code_axe})</span></td>
                  <td>{formatNumber(r.produits)} F</td>
                  <td>{formatNumber(r.charges)} F</td>
                  <td>{formatNumber(r.marge)} F</td>
                  <td>{r.taux_marge !== null ? formatNumber(r.taux_marge) : "—"} %</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {closed.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("controleGestion.clotures")} · {closed.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {closed.map((c) => <ClotureCard key={c.id} c={c} />)}
          </div>
        </>
      ) : null}

      {revs.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("controleGestion.revisions")} · {revs.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {revs.map((r) => <RevisionCard key={r.id} r={r} />)}
          </div>
        </>
      ) : null}

      <p className="muted" style={{ marginTop: "0.5rem" }}>
        {t("controleGestion.pendingNote")}
      </p>
    </>
  );
}