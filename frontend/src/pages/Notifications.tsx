import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff, CheckCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, DataGrid, ErrorState, PageHeader, notify } from "../components/ui";
import type { BadgeTone, GridColumn } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import type { NotificationItem } from "../types";

const KIND_TONE: Record<NotificationItem["kind"], BadgeTone> = {
  reminder: "warn",
  escalation: "err",
  info: "neutral",
};

type Filtre = "toutes" | "non_lues";

/** Notifications des circuits de validation (RF-34/35/37) : relances, escalades, informations. */
export function NotificationsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [filtre, setFiltre] = useState<Filtre>("toutes");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["notifications"],
    queryFn: api.notifications,
  });

  const lire = useMutation({
    mutationFn: (id: string) => api.post<NotificationItem>(`/api/workflow/notifications/${id}/mark_read/`),
    onSuccess: () => {
      notify.success(t("shell.notif.marqueeLue"));
      void qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e) => notify.error(t("shell.notif.erreur"), { description: describeError(e) }),
  });
  const toutLire = useMutation({
    mutationFn: () => api.post<{ updated: number }>("/api/workflow/notifications/mark_all_read/"),
    onSuccess: () => {
      notify.success(t("shell.notif.toutLuOk"));
      void qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e) => notify.error(t("shell.notif.erreur"), { description: describeError(e) }),
  });

  const all = data ?? [];
  const unread = all.filter((n) => !n.is_read).length;
  const rows = useMemo(() => (filtre === "non_lues" ? all.filter((n) => !n.is_read) : all), [all, filtre]);

  const columns: GridColumn<NotificationItem>[] = [
    {
      key: "objet",
      header: t("shell.notif.objet"),
      sortValue: (n) => n.subject,
      render: (n) => (
        <div className={n.is_read ? "notif-cell" : "notif-cell is-unread"}>
          <span className="notif-dot" aria-hidden="true" />
          <div className="notif-text">
            <span className="notif-subject">{n.subject}</span>
            <span className="notif-msg">
              {n.message}
              {n.document_title ? ` · ${n.document_title}` : ""}
            </span>
          </div>
          <span className="sr-only">{n.is_read ? t("shell.notif.lue") : t("shell.notif.nonLue")}</span>
        </div>
      ),
    },
    {
      key: "type",
      header: t("shell.notif.type"),
      width: 140,
      sortValue: (n) => n.kind,
      render: (n) => <Badge tone={KIND_TONE[n.kind] ?? "neutral"}>{t(`notifications.kind.${n.kind}`)}</Badge>,
    },
    {
      key: "recue",
      header: t("shell.notif.recue"),
      width: 190,
      sortValue: (n) => n.created_at,
      render: (n) => <span className="num">{formatDateTime(n.created_at)}</span>,
    },
  ];

  if (isError)
    return <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />;

  return (
    <>
      <PageHeader
        title={t("notifications.title")}
        subtitle={
          all.length && unread
            ? t("shell.notif.sousTitreNonLues", { count: unread, total: all.length })
            : t("shell.notif.sousTitre")
        }
        actions={
          unread > 0 ? (
            <button type="button" className="btn" onClick={() => toutLire.mutate()} disabled={toutLire.isPending}>
              <CheckCheck size={15} aria-hidden="true" />
              {t("shell.notif.toutLu")}
            </button>
          ) : null
        }
      />

      <div className="card shell-card-flush">
        <div className="shell-toolbar">
          <div className="seg" role="group" aria-label={t("shell.notif.filtre")}>
            {(["toutes", "non_lues"] as const).map((f) => (
              <button key={f} type="button" aria-pressed={filtre === f} onClick={() => setFiltre(f)}>
                {f === "toutes" ? t("shell.notif.toutes") : t("shell.notif.nonLues")}
                <span className="seg-count">{f === "toutes" ? all.length : unread}</span>
              </button>
            ))}
          </div>
        </div>
        <DataGrid
          columns={columns}
          rows={rows}
          loading={isLoading}
          caption={t("notifications.title")}
          initialSort={{ id: "recue", desc: true }}
          emptyIcon={BellOff}
          emptyLabel={filtre === "non_lues" ? t("shell.notif.videNonLues") : t("shell.notif.vide")}
          emptyHint={filtre === "non_lues" ? undefined : t("shell.notif.videAide")}
          rowActions={(n) => (n.is_read ? [] : [{ label: t("shell.notif.marquerLu"), icon: CheckCheck, onSelect: () => lire.mutate(n.id) }])}
        />
      </div>
    </>
  );
}
