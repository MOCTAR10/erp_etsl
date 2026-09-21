import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { MotionGrid, MotionItem } from "../components/Pilot";
import { formatBytes, formatDate } from "../lib/format";

function KpiCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <MotionItem>
      <div className="card kpi">
        <span className="kpi-label">{label}</span>
        <span className="kpi-value">{value}</span>
        {hint ? <span className="kpi-hint">{hint}</span> : null}
      </div>
    </MotionItem>
  );
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  if (isLoading) return <p className="muted">{t("common.loading")}</p>;
  if (isError || !data)
    return (
      <p>
        {t("common.error")}{" "}
        <button className="btn ghost" onClick={() => void refetch()}>
          {t("common.retry")}
        </button>
      </p>
    );

  const avg = data.workflow.avg_processing_days;
  const topTypes = data.documents.by_type.slice(0, 5);

  return (
    <>
      <h2>{t("dashboard.title")}</h2>
      <MotionGrid>
        <KpiCard label={t("dashboard.documents")} value={data.documents.total} />
        <KpiCard label={t("dashboard.storage")} value={formatBytes(data.documents.storage_bytes)} />
        <KpiCard label={t("dashboard.workflowPending")} value={data.workflow.pending} />
        <KpiCard
          label={t("dashboard.overdue")}
          value={data.workflow.overdue}
          hint={data.workflow.overdue ? "⚠" : undefined}
        />
        <KpiCard
          label={t("dashboard.avgDays")}
          value={avg === null ? "—" : `${avg}`}
          hint={avg === null ? undefined : t("dashboard.processedIn")}
        />
        <KpiCard
          label={t("dashboard.retention")}
          value={data.retention.due_count}
          hint={t("dashboard.retentionDue")}
        />
      </MotionGrid>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", alignItems: "start" }}>
        <MotionItem>
          <div className="card">
            <h3 style={{ fontSize: 15 }}>{t("dashboard.byType")}</h3>
            {topTypes.length === 0 ? (
              <p className="muted">{t("common.empty")}</p>
            ) : (
              topTypes.map((row) => (
                <div key={row.type__label} style={{ display: "flex", justifyContent: "space-between", padding: "0.35rem 0" }}>
                  <span>{row.type__label || "—"}</span>
                  <span className="badge brand">{row.count}</span>
                </div>
              ))
            )}
          </div>
        </MotionItem>

        <MotionItem>
          <div className="card">
            <h3 style={{ fontSize: 15 }}>{t("dashboard.retention")}</h3>
            {data.retention.due.length === 0 ? (
              <p className="muted">{t("common.empty")}</p>
            ) : (
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
            )}
          </div>
        </MotionItem>
      </div>
    </>
  );
}