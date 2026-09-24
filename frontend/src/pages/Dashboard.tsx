import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Archive, FileText, HardDrive, ListChecks, Timer } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { paletteFor } from "../theme/tokens";
import { useThemeMode } from "../lib/useThemeMode";
import { formatBytes, formatDate } from "../lib/format";
import { ChartCard, ErrorState, Kpi, KpiGridSkeleton, PageHeader, SectionCard } from "../components/ui";

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const mode = useThemeMode();
  const c = paletteFor(mode);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  if (isLoading) return <KpiGridSkeleton count={6} />;
  if (isError || !data)
    return <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />;

  const avg = data.workflow.avg_processing_days;
  const chart: ReturnType<typeof paletteFor> = c;
  const chartData = data.documents.by_type.slice(0, 6).map((row) => ({
    name: row.type__label || "—",
    count: row.count,
  }));
  const tooltipStyle = {
    background: chart.surface,
    border: `1px solid ${chart.border}`,
    borderRadius: "10px",
    color: chart.text,
    fontSize: 13,
  };

  return (
    <>
      <PageHeader title={t("dashboard.title")} />
      <div className="kpi-grid">
        <Kpi label={t("dashboard.documents")} value={data.documents.total} icon={FileText} tone="brand" delay={0} />
        <Kpi label={t("dashboard.storage")} value={data.documents.storage_bytes} format={formatBytes} icon={HardDrive} tone="brand" delay={0.05} />
        <Kpi label={t("dashboard.workflowPending")} value={data.workflow.pending} icon={ListChecks} tone="brand" delay={0.1} />
        <Kpi label={t("dashboard.overdue")} value={data.workflow.overdue} icon={data.workflow.overdue ? AlertTriangle : ListChecks} tone={data.workflow.overdue ? "err" : "brand"} delay={0.15} />
        <Kpi label={t("dashboard.avgDays")} value={avg === null ? "—" : avg} icon={Timer} tone="accent" delay={0.2} />
        <Kpi label={t("dashboard.retention")} value={data.retention.due_count} hint={t("dashboard.retentionDue")} icon={Archive} tone="warn" delay={0.25} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1rem", alignItems: "start" }}>
        <ChartCard title={t("dashboard.byType")} height={230}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
              <CartesianGrid stroke={chart.border} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" stroke={chart.textMuted} fontSize={12} tickLine={false} axisLine={false} angle={-18} textAnchor="end" height={46} interval={0} />
              <YAxis stroke={chart.textMuted} fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill={chart.brand} radius={[6, 6, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <SectionCard title={t("dashboard.retention")} subtitle={`${data.retention.due.length} ${t("dashboard.retentionDue")}`}>
          {data.retention.due.length === 0 ? (
            <p className="muted">{t("common.empty")}</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("dashboard.documents")}</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {data.retention.due.map((d) => (
                    <tr key={d.id}>
                      <td>
                        {d.titre} <span className="muted">· {d.type}</span>
                      </td>
                      <td className="muted">{formatDate(d.retention_fin, i18n.language)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </>
  );
}