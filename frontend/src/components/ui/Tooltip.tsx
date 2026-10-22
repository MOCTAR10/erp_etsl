import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";

/**
 * Infobulle (Radix Tooltip) : à l'entrée du pointeur ou au focus clavier, fermée par Échap ;
 * reliée au déclencheur par `aria-describedby`. Pour un `.icon-btn`, garder un `aria-label`
 * (l'infobulle complète le nom accessible, elle ne le remplace pas).
 */
export function Tooltip({
  content,
  children,
  side = "top",
  align = "center",
  delay = 350,
}: {
  content: ReactNode;
  /** UN élément focusable (reçu via `asChild`). */
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  /** Délai d'ouverture au survol (ms). */
  delay?: number;
}) {
  return (
    <RadixTooltip.Provider delayDuration={delay} skipDelayDuration={250}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content className="ui-tooltip ui-pop" side={side} align={align} sideOffset={6} collisionPadding={8}>
            {content}
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
