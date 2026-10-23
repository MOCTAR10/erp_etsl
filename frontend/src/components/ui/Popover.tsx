import * as RadixPopover from "@radix-ui/react-popover";
import type { ReactElement, ReactNode } from "react";

/**
 * Fenêtre flottante générique (Radix Popover) : filtres, sélecteurs, détails. Focus déplacé dans le contenu
 * à l'ouverture, Échap / clic extérieur ferment, focus rendu au déclencheur.
 */
export function Popover({
  trigger,
  children,
  open,
  onOpenChange,
  side = "bottom",
  align = "start",
  label,
  className,
  onOpenAutoFocus,
}: {
  /** UN élément focusable (reçu via `asChild`). */
  trigger: ReactElement;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  /** Nom accessible du contenu (role="dialog"). */
  label?: string;
  className?: string;
  onOpenAutoFocus?: (event: Event) => void;
}) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          className={`ui-popover ui-pop ${className ?? ""}`.trim()}
          side={side}
          align={align}
          sideOffset={8}
          collisionPadding={12}
          aria-label={label}
          onOpenAutoFocus={onOpenAutoFocus}
        >
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
