import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { formatDateTime } from "../lib/format";
import type { NotificationItem } from "../types";
import { Popover, Tooltip } from "./ui";

/** Nombre d'éléments de l'aperçu : la liste complète reste sur /notifications. */
const APERCU = 5;

/**
 * Cloche de la barre du haut : compteur des non lues et aperçu des dernières notifications, sans quitter la page.
 * Partage le cache `["notifications"]` de la coquille et de l'écran Notifications (aucune requête en plus).
 */
export function NotificationBell({ items }: { items: NotificationItem[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const nonLues = items.filter((n) => !n.is_read);
  // Les non lues d'abord ; à défaut, les plus récentes (l'API les sert déjà du plus récent au plus ancien).
  const apercu = (nonLues.length ? nonLues : items).slice(0, APERCU);
  const rafraichir = () => void qc.invalidateQueries({ queryKey: ["notifications"] });

  const lire = useMutation({
    mutationFn: (id: string) => api.post<NotificationItem>(`/api/workflow/notifications/${id}/mark_read/`),
    onSuccess: rafraichir,
  });
  const toutLire = useMutation({
    mutationFn: () => api.post<{ updated: number }>("/api/workflow/notifications/mark_all_read/"),
    onSuccess: rafraichir,
  });

  const voirTout = () => {
    setOpen(false);
    navigate("/notifications");
  };

  const libelle = nonLues.length
    ? t("shell.notif.clocheNonLues", { count: nonLues.length })
    : t("nav.notifications");

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      align="end"
      label={t("nav.notifications")}
      className="notif-pop"
      trigger={
        <button type="button" className="icon-btn topbar-bell" aria-label={libelle}>
          <Bell size={16} aria-hidden="true" />
          {nonLues.length > 0 && (
            <span className="topbar-bell-count" aria-hidden="true">
              {nonLues.length > 99 ? "99+" : nonLues.length}
            </span>
          )}
        </button>
      }
    >
      <div className="notif-pop-head">
        <strong>{t("nav.notifications")}</strong>
        {nonLues.length > 0 && (
          <Tooltip content={t("shell.notif.toutLu")} side="bottom">
            <button
              type="button"
              className="icon-btn"
              aria-label={t("shell.notif.toutLu")}
              disabled={toutLire.isPending}
              onClick={() => toutLire.mutate()}
            >
              <CheckCheck size={15} aria-hidden="true" />
            </button>
          </Tooltip>
        )}
      </div>
      {apercu.length === 0 ? (
        <p className="notif-pop-vide">{t("shell.notif.vide")}</p>
      ) : (
        <ul className="notif-pop-list">
          {apercu.map((n) => (
            <li key={n.id}>
              <button
                type="button"
                className={n.is_read ? "notif-pop-item" : "notif-pop-item is-unread"}
                onClick={() => {
                  if (!n.is_read) lire.mutate(n.id);
                  voirTout();
                }}
              >
                <span className="notif-pop-subject">{n.subject}</span>
                {n.document_title && <span className="notif-pop-doc">{n.document_title}</span>}
                <span className="notif-pop-date">{formatDateTime(n.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="notif-pop-all" onClick={voirTout}>
        {t("shell.notif.voirTout")}
      </button>
    </Popover>
  );
}
