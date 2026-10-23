import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { MoreHorizontal } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useTranslation } from "react-i18next";

/** Entrée d'action d'un menu. */
export interface MenuItemDef {
  /** Clé React stable (sinon l'index). */
  id?: string;
  label: ReactNode;
  icon?: LucideIcon;
  onSelect?: () => void;
  /** Raccourci affiché à droite (indicatif, ex. « Ctrl+E ») ; le menu ne le capte pas. */
  shortcut?: string;
  /** Action destructive (suppression, annulation) : rendu en rouge sémantique. */
  danger?: boolean;
  disabled?: boolean;
}

/** Titre de section non cliquable. */
export interface MenuLabelDef {
  type: "label";
  label: ReactNode;
}

/** Une entrée : action, séparateur (`"separator"`) ou titre de section. Les `false`/`null` sont ignorés (entrées conditionnelles). */
export type MenuEntry = MenuItemDef | MenuLabelDef | "separator" | false | null | undefined;

const isLabel = (e: MenuItemDef | MenuLabelDef): e is MenuLabelDef => (e as MenuLabelDef).type === "label";

/**
 * Menu déroulant d'actions (Radix DropdownMenu) : navigation clavier (↑ ↓ Entrée Échap, saisie d'une lettre),
 * focus rendu au déclencheur. Sans `trigger` : bouton icône « ⋯ » (`.icon-btn`) libellé par `label`.
 * Le clic sur le déclencheur ne remonte pas (utilisable dans une ligne de tableau ou une carte cliquable).
 */
export function Menu({
  items,
  label,
  trigger,
  align = "end",
  side = "bottom",
  size = "md",
}: {
  items: MenuEntry[];
  /** Nom accessible du bouton « ⋯ » (défaut : « Plus d'actions »). */
  label?: string;
  /** Déclencheur personnalisé : UN élément focusable (bouton), reçu via `asChild`. */
  trigger?: ReactElement;
  align?: "start" | "center" | "end";
  side?: "top" | "right" | "bottom" | "left";
  /** `sm` : bouton « ⋯ » compact (lignes de tableau denses, cartes kanban). */
  size?: "sm" | "md";
}) {
  const { t } = useTranslation();
  const entries = items.filter(Boolean) as (MenuItemDef | MenuLabelDef | "separator")[];
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild onClick={(e) => e.stopPropagation()}>
        {trigger ?? (
          <button type="button" className={`icon-btn ui-menu-trigger${size === "sm" ? " sm" : ""}`} aria-label={label ?? t("ui.moreActions")}>
            <MoreHorizontal size={size === "sm" ? 15 : 17} aria-hidden />
          </button>
        )}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="ui-menu ui-pop"
          align={align}
          side={side}
          sideOffset={6}
          collisionPadding={12}
          onClick={(e) => e.stopPropagation()}
        >
          {entries.map((entry, i) => {
            if (entry === "separator") return <DropdownMenu.Separator key={`sep-${i}`} className="ui-menu-sep" />;
            if (isLabel(entry)) {
              return (
                <DropdownMenu.Label key={`lbl-${i}`} className="ui-menu-label">
                  {entry.label}
                </DropdownMenu.Label>
              );
            }
            const Icon = entry.icon;
            return (
              <DropdownMenu.Item
                key={entry.id ?? i}
                className={`ui-menu-item${entry.danger ? " danger" : ""}`}
                disabled={entry.disabled}
                onSelect={() => entry.onSelect?.()}
              >
                <span className="ui-menu-icon" aria-hidden>
                  {Icon ? <Icon size={15} /> : null}
                </span>
                <span className="ui-menu-text">{entry.label}</span>
                {entry.shortcut ? <kbd className="ui-kbd">{entry.shortcut}</kbd> : null}
              </DropdownMenu.Item>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
