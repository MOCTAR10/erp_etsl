import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Archive, FileText, ListChecks, SlidersHorizontal, Timer } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { paletteFor } from "../theme/tokens";
import { useThemeMode } from "../lib/useThemeMode";
import { formatDate, formatNumber } from "../lib/format";
import { cleanLabel } from "../components/workflow/libelle";
import { DataGrid, EmptyState, ErrorState, Kpi, KpiGridSkeleton, PageHeader, SectionCard } from "../components/ui";
import type { GridColumn } from "../components/ui";
import { useAuth } from "../store/auth";

/**
 * Rôles qui voient le bandeau « paramètres provisoires à confirmer par ETSL » (écarts transverses) : l'administration
 * technique seulement (A-02) — rien en tête d'écran pour la Direction, qui confirme depuis « Paramètres ETSL ».
 */
const ROLES_PARAMETRES = ["admin"];
/** Longueur maximale d'un libellé d'axe (le libellé complet reste dans l'infobulle). */
const MAX_LABEL = 30;
const BAR_ROW = 34;

const court = (s: string) => (s.length > MAX_LABEL ? `${s.slice(0, MAX_LABEL - 1).trimEnd()}…` : s);

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const mode = useThemeMode();
  const c = paletteFor(mode);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });
  const role = useAuth((s) => s.user?.role) ?? "";
  const resume = useQuery({
    queryKey: ["parametres-etsl-resume"],
    queryFn: api.parametresEtslResume,
    enabled: ROLES_PARAMETRES.includes(role),
    retry: 0,
  }).data;

  const header = <PageHeader title={t("dashboard.title")} subtitle={t("dashboard.subtitle")} />;
  if (isLoading)
    return (
      <>
        {header}
        <KpiGridSkeleton count={4} />
      </>
    );
  if (isError || !data)
    return (
      <>
        {header}
        <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />
      </>
    );

  const avg = data.workflow.avg_processing_days;
  const archives = data.documents.by_status?.archived ?? 0;
  // Répartition : triée décroissante, type vide nommé « Non classé », libellés sans référence d'exigence.
  const chartData = data.documents.by_type
    .map((row) => ({ name: row.type__label ? cleanLabel(row.type__label) : t("dashboard2.nonClasse"), count: row.count }))
    .sort((x, y) => y.count - x.count)
    .slice(0, 8);
  const retentionRows = data.retention.due.map((d) => ({ ...d, id: d.id }));
  const retentionCols: GridColumn<(typeof retentionRows)[number]>[] = [
    {
      key: "doc",
      header: t("dashboard.documents"),
      render: (d) => (
        <>
          <strong>{d.titre}</strong> <span className="muted">· {cleanLabel(d.type)}</span>
        </>
      ),
      sortValue: (d) => d.titre,
    },
    { key: "fin", header: t("dashboard2.finConservation"), render: (d) => formatDate(d.retention_fin, i18n.language), sortValue: (d) => d.retention_fin },
  ];

  return (
    <>
      {header}

      {resume && resume.provisoires > 0 ? (
        <div className="banner warn" role="status" data-testid="kpi-parametres-provisoires">
          <SlidersHorizontal size={18} aria-hidden />
          <div className="banner-body">
            <strong className="banner-title">{t("dashboard2.provisoires", { count: resume.provisoires })}</strong>
            <span className="banner-text">{t("dashboard2.provisoiresTexte")}</span>
          </div>
          <Link className="banner-action" to="/parametres">
            {t("direction2.ouvrirParametres")}
          </Link>
        </div>
      ) : null}

      <div className="kpi-grid">
        <Kpi
          label={t("dashboard.documents")}
          value={data.documents.total}
          hint={t("dashboard2.archives", { count: archives })}
          icon={FileText}
          tone="brand"
          delay={0}
        />
        <Kpi
          label={t("dashboard.workflowPending")}
          value={data.workflow.pending}
          hint={data.workflow.overdue ? t("dashboard2.enRetard", { count: data.workflow.overdue }) : t("dashboard2.aucunRetard")}
          icon={data.workflow.overdue ? AlertTriangle : ListChecks}
          tone={data.workflow.overdue ? "err" : "brand"}
          delay={0.04}
        />
        <Kpi
          label={t("dashboard.avgDays")}
          value={avg === null ? "—" : t("dashboard2.jours", { n: formatNumber(avg, { decimals: avg % 1 ? 1 : 0 }) })}
          hint={avg === null ? t("dashboard2.aucunCircuitTermine") : t("dashboard2.parValidation")}
          icon={Timer}
          tone="neutral"
          delay={0.08}
        />
        <Kpi
          label={t("dashboard.retention")}
          value={data.retention.due_count}
          hint={t("dashboard.retentionDue")}
          icon={Archive}
          tone={data.retention.due_count ? "warn" : "neutral"}
          delay={0.12}
        />
      </div>

      <div className="dash-split">
        <SectionCard title={t("dashboard.byType")} subtitle={t("dashboard2.byTypeSub", { count: data.documents.total })}>
          {chartData.length === 0 ? (
            <EmptyState label={t("common.empty")} compact />
          ) : (
            <div style={{ height: chartData.length * BAR_ROW + 8 }} role="img" aria-label={chartData.map((r) => `${r.name} ${r.count}`).join(", ")}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 40, left: 0, bottom: 0 }} barCategoryGap={8}>
                  <XAxis type="number" hide allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={210}
                    tickLine={false}
                    axisLine={false}
                    stroke={c.textMuted}
                    fontSize={12.5}
                    tickFormatter={court}
                  />
                  <Tooltip
                    cursor={{ fill: c.brandSoft }}
                    contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, color: c.text, fontSize: 12 }}
                    formatter={(v) => [formatNumber(Number(v)), t("dashboard.documents")]}
                  />
                  <Bar dataKey="count" fill={c.brand} radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false}>
                    <LabelList dataKey="count" position="right" fill={c.text} fontSize={12} formatter={(v: unknown) => formatNumber(Number(v))} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard title={t("dashboard.retention")} subtitle={t("dashboard2.retentionSub", { count: data.retention.due.length })}>
          {retentionRows.length === 0 ? (
            <EmptyState icon={Archive} label={t("dashboard2.retentionVide")} hint={t("dashboard2.retentionVideHint")} />
          ) : (
            <DataGrid columns={retentionCols} rows={retentionRows} caption={t("dashboard.retention")} density="compact" maxHeight={360} />
          )}
        </SectionCard>
      </div>
    </>
  );
}
