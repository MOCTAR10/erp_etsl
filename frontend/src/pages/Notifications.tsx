import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDateTime } from "../lib/format";

const KINDS_BADGE: Record<string, string> = {
  reminder: "warn",
  escalation: "err",
  info: "brand",
};

export function NotificationsPage() {
  const { t, i18n } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["notifications"],
    queryFn: api.notifications,
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

  const unread = data.filter((n) => !n.is_read).length;

  return (
    <>
      <h2>
        {t("notifications.title")}
        {unread > 0 ? (
          <span className="badge err" style={{ marginLeft: "0.6rem", verticalAlign: "middle" }}>
            {unread} {t("notifications.unread")}
          </span>
        ) : null}
      </h2>
      {data.length === 0 ? (
        <p className="muted">{t("common.empty")}</p>
      ) : (
        data.map((n) => (
          <div className="card" key={n.id} style={{ marginBottom: "0.7rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
              <strong>{n.subject}</strong>
              <span className={`badge ${KINDS_BADGE[n.kind] ?? "brand"}`}>
                {t(`notifications.kind.${n.kind}`)}
              </span>
            </div>
            <p className="muted mt-1" style={{ margin: "0.3rem 0" }}>
              {n.message}
              {n.document_title ? <span className="muted"> · {n.document_title}</span> : null}
            </p>
            <div className="muted" style={{ fontSize: 12 }}>
              {formatDateTime(n.created_at, i18n.language)} —{" "}
              {n.is_read ? "✓" : "✉"}
            </div>
          </div>
        ))
      )}
    </>
  );
}