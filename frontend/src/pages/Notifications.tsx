import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BellOff, CheckCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Badge, DataGrid, EmptyState, ErrorState, PageHeader, SectionTitle, notify } from "../components/ui";
import type { BadgeTone, GridColumn } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import { roleLabel } from "../lib/roles";
import type { NotificationItem } from "../types";

// Escalade = à traiter, pas une panne : ambre comme la relance (le rouge reste réservé aux erreurs).
const KIND_TONE: Record<NotificationItem["kind"], BadgeTone> = {
  reminder: "warn",
  escalation: "warn",
  info: "neutral",
};

type Filtre = "toutes" | "non_lues";
type Groupe = "aujourdhui" | "semaine" | "ancien";
const GROUPES: Groupe[] = ["aujourdhui", "semaine", "ancien"];
const JOUR_MS = 86_400_000;

/** Regroupement par jour de réception : aujourd'hui, 7 derniers jours, plus ancien. */
export function groupeDe(iso: string, now: Date = new Date()): Groupe {
  const d = new Date(iso);
  if (d.toDateString() === now.toDateString()) return "aujourdhui";
  return now.getTime() - d.getTime() < 7 * JOUR_MS ? "semaine" : "ancien";
}

/** Jours de retard de la tâche liée (0 si à l'heure ou sans tâche). */
export function joursRetard(due: string | null | undefined, now: Date = new Date()): number {
  if (!due) return 0;
  return Math.max(0, Math.floor((now.getTime() - new Date(due).getTime()) / JOUR_MS));
}

/** Notifications des circuits de validation (RF-34/35/37) : relances, escalades, informations. */
export function NotificationsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [filtre, setFiltre] = useState<Filtre>("toutes");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["notifications"],
    queryFn: api.notifications,
  });
  // Boîte vide : on oriente vers les validations en retard plutôt qu'un écran « non branché » (A-05).
  const taches = useQuery({ queryKey: ["tasks"], queryFn: api.tasks, staleTime: 60_000 });
  const enRetard = (taches.data ?? []).filter(
    (tk) => (tk.status === "pending" || tk.status === "delegated") && new Date(tk.due_date) < new Date(),
  ).length;

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

  const groupes = useMemo(() => {
    const now = new Date();
    return GROUPES.map((g) => ({ g, items: rows.filter((n) => groupeDe(n.created_at, now) === g) })).filter((x) => x.items.length);
  }, [rows]);

  /** Sous-titre compact : « étape · en retard depuis 5 j · service » (le corps libre répétait le document). */
  const sousTitre = (n: NotificationItem) => {
    if (!n.document_title) return n.message;
    const retard = joursRetard(n.task_due_date);
    return [n.step_name, retard ? t("vague3B.notif.retard", { count: retard }) : null, roleLabel(t, n.step_role)]
      .filter(Boolean)
      .join(" · ");
  };

  const columns: GridColumn<NotificationItem>[] = [
    {
      key: "objet",
      header: t("shell.notif.objet"),
      sortValue: (n) => n.document_title ?? n.subject,
      render: (n) => (
        <div className={n.is_read ? "notif-cell" : "notif-cell is-unread"}>
          <span className="notif-dot" aria-hidden="true" />
          <div className="notif-text">
            <span className="notif-subject">{n.document_title || n.subject}</span>
            <span className="notif-msg">{sousTitre(n)}</span>
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
    <div className="shell-page">
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
        {!isLoading && all.length === 0 ? (
          <EmptyState
            icon={BellOff}
            label={t("shell.notif.vide")}
            hint={t("shell.notif.videAide")}
            action={
              enRetard ? (
                <Link className="btn" to="/kanban">
                  {t("premiumPilotage.notifications.voirRetards", { count: enRetard })}
                  <ArrowRight size={15} aria-hidden />
                </Link>
              ) : undefined
            }
          />
        ) : isLoading || groupes.length === 0 ? (
          <DataGrid
            columns={columns}
            rows={[]}
            loading={isLoading}
            caption={t("notifications.title")}
            emptyIcon={BellOff}
            emptyLabel={filtre === "non_lues" ? t("shell.notif.videNonLues") : t("shell.notif.vide")}
            emptyHint={filtre === "non_lues" ? undefined : t("shell.notif.videAide")}
          />
        ) : (
          groupes.map(({ g, items }) => (
            <section key={g} className="notif-group" aria-label={t(`vague3B.notif.groupes.${g}`)}>
              <div className="shell-toolbar">
                <SectionTitle>
                  {t(`vague3B.notif.groupes.${g}`)} <span className="seg-count">{items.length}</span>
                </SectionTitle>
              </div>
              <DataGrid
                columns={columns}
                rows={items}
                caption={`${t("notifications.title")} — ${t(`vague3B.notif.groupes.${g}`)}`}
                initialSort={{ id: "recue", desc: true }}
                rowActions={(n) => (n.is_read ? [] : [{ label: t("shell.notif.marquerLu"), icon: CheckCheck, onSelect: () => lire.mutate(n.id) }])}
              />
            </section>
          ))
        )}
      </div>
    </div>
  );
}
