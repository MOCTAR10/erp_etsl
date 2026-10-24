import { ChevronDown, Settings2 } from "lucide-react";
import { useId, useState } from "react";
import type { FocusEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";

export interface ModuleSettingsProps {
  /** `id` de la section (cible de l'ancre « Paramètres » de la `SectionNav`) ; sert aussi de clé de mémorisation. */
  id: string;
  /** Titre (défaut « Paramètres du module »). */
  title?: ReactNode;
  /** Phrase d'aide sous le titre (défaut : référentiels, barèmes et valeurs provisoires). */
  hint?: ReactNode;
  /** Ouvert au premier affichage (défaut : replié). */
  defaultOpen?: boolean;
  children: ReactNode;
}

const STORAGE_PREFIX = "etls.moduleSettings.";

function readOpen(id: string, fallback: boolean): boolean {
  try {
    const v = window.localStorage.getItem(STORAGE_PREFIX + id);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

function writeOpen(id: string, open: boolean) {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + id, open ? "1" : "0");
  } catch {
    // Stockage indisponible (navigation privée, aperçu) : l'état reste en mémoire.
  }
}

/**
 * Section « Paramètres du module » repliée en bas d'un écran métier (B11) : référentiels, barèmes, gabarits et
 * paramètres provisoires sortent du fil de lecture de la page. Le contenu n'est monté qu'une fois déplié (pages plus
 * courtes et moins de requêtes) ; l'état est mémorisé par écran dans le navigateur. Un saut de la `SectionNav` vers
 * la section (focus posé sur elle) la déplie.
 * `<ModuleSettings id="qa-parametres"><ParametresQualiteSection /></ModuleSettings>`
 */
export function ModuleSettings({ id, title, hint, defaultOpen = false, children }: ModuleSettingsProps) {
  const { t } = useTranslation();
  const uid = useId();
  const [open, setOpen] = useState(() => readOpen(id, defaultOpen));
  const headId = `${uid}-titre`;
  const bodyId = `${uid}-contenu`;
  const toggle = (next: boolean) => {
    setOpen(next);
    writeOpen(id, next);
  };
  const onFocus = (e: FocusEvent<HTMLElement>) => {
    if (e.target === e.currentTarget && !open) toggle(true);
  };
  return (
    <section id={id} className={`page-section ui-modsettings${open ? " is-open" : ""}`} aria-labelledby={headId} onFocus={onFocus} data-testid="module-settings">
      <div className="ui-modsettings-bar">
        <span className="ui-modsettings-icon" aria-hidden="true">
          <Settings2 size={18} />
        </span>
        <div className="ui-modsettings-text">
          <h3 id={headId} className="ui-modsettings-title">
            {title ?? t("premiumKit.moduleSettings.title")}
          </h3>
          <p className="ui-modsettings-hint">{hint ?? t("premiumKit.moduleSettings.hint")}</p>
        </div>
        <button type="button" className="btn ghost sm ui-modsettings-toggle" aria-expanded={open} aria-controls={bodyId} onClick={() => toggle(!open)}>
          {open ? t("premiumKit.moduleSettings.masquer") : t("premiumKit.moduleSettings.afficher")}
          <ChevronDown size={14} aria-hidden="true" className="ui-modsettings-chevron" />
        </button>
      </div>
      <div id={bodyId} className="ui-modsettings-body" hidden={!open}>
        {open ? children : null}
      </div>
    </section>
  );
}
