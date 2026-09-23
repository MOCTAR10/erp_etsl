import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
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

function BudgetCard({ b }: { b: Budget }) {
  const { t } = useTranslation();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="task-card"
    >
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
    </motion.div>
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
    return <p className="muted">{t("common.loading")}</p>;

  if (budgets.isError || marges.isError || cloturesStats.isError)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void budgets.refetch();
            void revisions.refetch();
            void clotures.refetch();
            void cloturesStats.refetch();
            void marges.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
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
      <h2>{t("controleGestion.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("controleGestion.budgets")}</span>
          <span className="kpi-value">{enCours}</span>
          <span className="meta muted">{t("controleGestion.variance")}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("controleGestion.revisions")}</span>
          <span className="kpi-value">{appliquees}</span>
          <span className="meta muted">R1 - R4</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("controleGestion.clotures")}</span>
          <span className="kpi-value">
            {stats ? `${stats.conformes_j4}/${stats.periodes}` : "—"}
          </span>
          <span className="meta muted">{t("controleGestion.realizeesJ4")}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("controleGestion.marge")}</span>
          <span className="kpi-value">
            {m && m.totals.marge_hors_gr !== null ? `${formatNumber(m.totals.marge_hors_gr)} F` : "••••••"}
          </span>
          <span className="meta muted">{t("controleGestion.coutGr")} {m ? formatNumber(m.totals.cout_gr) : "—"} F</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {BUD_ORDER.map((st) => (
          <motion.div
            key={st}
            layout
            className="board-col"
            style={{ minWidth: 280 }}
            initial={{ opacity: 0, y: motionTokens.distance.sm }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
          >
            <div className="board-col-head">
              <span>{t(`controleGestion.statut_budget.${st}`)}</span>
              <span className={`badge ${BUD_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((b) => <BudgetCard key={b.id} b={b} />)
            )}
          </motion.div>
        ))}
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