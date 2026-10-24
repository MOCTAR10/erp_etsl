import { BadgeCheck, ChevronDown, CircleDashed, ExternalLink } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Badge } from "../ui";

/**
 * Panneau compact des paramètres provisoires d'un écran métier (B05) : une ligne « N paramètres provisoires à
 * confirmer » + « Afficher » (replié par défaut) qui révèle le tableau existant, et un lien vers la page centrale
 * « Paramètres ETSL » ouverte sur le module. Le tableau reste monté (requêtes et compteurs inchangés), seulement masqué.
 */
export function ParamsPanel({
  module,
  count,
  total,
  title,
  testId,
  alertTestId,
  defaultOpen = false,
  variant = "inline",
  children,
}: {
  /** `card` : panneau autonome entre deux cartes de la page (même espacement qu'une carte) ; `inline` : dans une carte. */
  variant?: "inline" | "card";
  /** Libellé d'application Django (`controle_gestion`, `rh_paie`…) : cible du lien `/parametres?module=…`. */
  module: string;
  /** Nombre de paramètres provisoires (undefined pendant le chargement). */
  count: number | undefined;
  /** Nombre total de paramètres du bloc (facultatif, affiché quand tout est confirmé). */
  total?: number;
  /** Nom court du bloc (« Paramètres de lettrage ») ; omis si la carte porte déjà ce titre. */
  title?: ReactNode;
  testId?: string;
  /** `data-testid` posé sur le résumé quand des paramètres sont provisoires (ancien bandeau d'alerte). */
  alertTestId?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const uid = useId();
  const [open, setOpen] = useState(defaultOpen);
  const pending = (count ?? 0) > 0;
  const bodyId = `${uid}-params`;
  const resume = pending
    ? t("premiumParams.panel.aConfirmer", { count })
    : total !== undefined
      ? t("premiumParams.panel.tousConfirmes", { count: total })
      : t("premiumParams.panel.confirmes");
  return (
    <div
      className={`${variant === "card" ? "card params-panel params-panel--card" : "params-panel"}${pending ? " is-pending" : ""}${open ? " is-open" : ""}`}
      data-testid={testId}
    >
      <div className="params-panel-bar">
        <span className="params-panel-icon" aria-hidden="true">
          {pending ? <CircleDashed size={16} /> : <BadgeCheck size={16} />}
        </span>
        <p className="params-panel-summary">
          {title ? <span className="params-panel-title">{title}</span> : null}
          <span data-testid={pending ? alertTestId : undefined}>{count === undefined ? t("common.loading") : resume}</span>
        </p>
        <div className="params-panel-actions">
          <button
            type="button"
            className="btn ghost sm params-panel-toggle"
            aria-expanded={open}
            aria-controls={bodyId}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? t("premiumParams.panel.masquer") : t("premiumParams.panel.afficher")}
            <ChevronDown size={14} aria-hidden="true" className="params-panel-chevron" />
          </button>
          <Link className="params-panel-link" to={`/parametres?module=${encodeURIComponent(module)}`}>
            {t("premiumParams.panel.gerer")}
            <ExternalLink size={13} aria-hidden="true" />
          </Link>
        </div>
      </div>
      <div id={bodyId} className="params-panel-body" hidden={!open}>
        {children}
      </div>
    </div>
  );
}

/** Statut court d'un paramètre : « Provisoire » (texte long en infobulle) ou « Confirmé » — motif partagé (A36). */
export function ParamStatusBadge({ provisoire, label }: { provisoire: boolean; label?: string }) {
  const { t } = useTranslation();
  return provisoire ? (
    <Badge tone="warn" title={t("premiumParams.badge.provisoireTitle")}>
      {t("premiumParams.badge.provisoire")}
    </Badge>
  ) : (
    <Badge tone="ok">{label ?? t("premiumParams.badge.confirme")}</Badge>
  );
}
