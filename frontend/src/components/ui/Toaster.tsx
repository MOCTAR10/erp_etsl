import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Toaster, toast } from "sonner";
import type { ExternalToast } from "sonner";

import { useThemeMode } from "../../lib/useThemeMode";

/**
 * Zone de notifications de l'application (sonner) — montée UNE fois dans `App.tsx`.
 * Bas-droite, thème clair/sombre suivant `data-theme`, couleurs de la charte (primitives.css, `.ui-toast`).
 */
export function AppToaster() {
  const { t } = useTranslation();
  const mode = useThemeMode();
  return (
    <Toaster
      position="bottom-right"
      theme={mode}
      closeButton
      visibleToasts={4}
      gap={10}
      offset={20}
      mobileOffset={12}
      containerAriaLabel={t("ui.notifications")}
      icons={{
        success: <CheckCircle2 size={18} aria-hidden />,
        error: <XCircle size={18} aria-hidden />,
        info: <Info size={18} aria-hidden />,
        warning: <AlertTriangle size={18} aria-hidden />,
        loading: <Loader2 size={18} className="ui-spin" aria-hidden />,
      }}
      toastOptions={{
        closeButtonAriaLabel: t("ui.close"),
        classNames: {
          toast: "ui-toast",
          title: "ui-toast-title",
          description: "ui-toast-desc",
          actionButton: "ui-toast-action",
          cancelButton: "ui-toast-cancel",
          closeButton: "ui-toast-close",
          success: "ui-toast--success",
          error: "ui-toast--error",
          info: "ui-toast--info",
          warning: "ui-toast--warning",
        },
      }}
    />
  );
}

export type NotifyOptions = Pick<ExternalToast, "description" | "duration" | "action" | "id">;

/**
 * Notifications applicatives — à appeler après une action (mutation réussie, erreur serveur, info).
 * `notify.success("Bon de commande émis", { description: "BC-2026-0042" })`.
 */
export const notify = {
  success: (message: ReactNode, opts?: NotifyOptions) => toast.success(message, opts),
  error: (message: ReactNode, opts?: NotifyOptions) => toast.error(message, { duration: 7000, ...opts }),
  info: (message: ReactNode, opts?: NotifyOptions) => toast.info(message, opts),
  warning: (message: ReactNode, opts?: NotifyOptions) => toast.warning(message, opts),
  /** Suit une promesse : chargement → succès / erreur (libellés fixes ou calculés). */
  promise: toast.promise,
  dismiss: (id?: string | number) => toast.dismiss(id),
};
