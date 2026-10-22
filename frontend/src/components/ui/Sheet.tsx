import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRef, useState } from "react";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { motionTokens } from "../../theme/tokens";

export interface SheetProps {
  /** Ouverture contrôlée (avec `onOpenChange`) ; sinon le composant gère son état, ouvert par `trigger`. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Déclencheur (UN élément focusable) : ouvre le panneau, reçoit le focus à la fermeture. */
  trigger?: ReactElement;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  /** Pied d'actions (boutons `.btn`), aligné à droite, collé en bas du panneau. */
  footer?: ReactNode;
  /** Largeur max. du panneau (défaut 520 px en latéral, 560 px en modale). */
  width?: number | string;
  /** Bloque la fermeture par clic extérieur (saisie en cours) ; Échap et ✕ restent actifs. */
  preventOutsideClose?: boolean;
  className?: string;
}

const transition = { duration: motionTokens.duration.base, ease: motionTokens.ease.out };

function SheetBase({ variant, ...p }: SheetProps & { variant: "sheet" | "modal" }) {
  const { t } = useTranslation();
  const [inner, setInner] = useState(false);
  const controlled = p.open !== undefined;
  const open = controlled ? Boolean(p.open) : inner;
  const setOpen = (v: boolean) => {
    if (!controlled) setInner(v);
    p.onOpenChange?.(v);
  };
  // Ouverture contrôlée sans `trigger` : on mémorise l'élément actif pour lui rendre le focus à la fermeture.
  const returnFocus = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  if (open && !wasOpen.current && typeof document !== "undefined") {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  wasOpen.current = open;
  const isSheet = variant === "sheet";
  const style = { "--ui-panel-w": typeof p.width === "number" ? `${p.width}px` : p.width } as CSSProperties;
  const panelMotion = isSheet
    ? { initial: { x: 48, opacity: 0 }, animate: { x: 0, opacity: 1 }, exit: { x: 48, opacity: 0 } }
    : {
        initial: { y: motionTokens.distance.md, scale: 0.97, opacity: 0 },
        animate: { y: 0, scale: 1, opacity: 1 },
        exit: { y: motionTokens.distance.sm, scale: 0.98, opacity: 0 },
      };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      {p.trigger ? <Dialog.Trigger asChild>{p.trigger}</Dialog.Trigger> : null}
      <AnimatePresence>
        {open ? (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div
                className="ui-overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: motionTokens.duration.fast }}
              />
            </Dialog.Overlay>
            <div className={isSheet ? "ui-sheet-pos" : "ui-modal-pos"}>
              <Dialog.Content
                asChild
                forceMount
                {...(p.description ? {} : { "aria-describedby": undefined })}
                onCloseAutoFocus={(e) => {
                  if (p.trigger || !returnFocus.current?.isConnected) return;
                  e.preventDefault();
                  returnFocus.current.focus();
                }}
                onPointerDownOutside={p.preventOutsideClose ? (e) => e.preventDefault() : undefined}
                onInteractOutside={p.preventOutsideClose ? (e) => e.preventDefault() : undefined}
              >
                <motion.div
                  className={`${isSheet ? "ui-sheet" : "ui-modal"} ui-panel ${p.className ?? ""}`.trim()}
                  style={p.width !== undefined ? style : undefined}
                  {...panelMotion}
                  transition={transition}
                >
                  <header className="ui-panel-head">
                    <div className="ui-panel-titles">
                      <Dialog.Title className="ui-panel-title">{p.title}</Dialog.Title>
                      {p.description ? <Dialog.Description className="ui-panel-desc">{p.description}</Dialog.Description> : null}
                    </div>
                    <Dialog.Close asChild>
                      <button type="button" className="icon-btn ui-panel-close" aria-label={t("ui.close")}>
                        <X size={16} aria-hidden />
                      </button>
                    </Dialog.Close>
                  </header>
                  {p.children ? <div className="ui-panel-body">{p.children}</div> : null}
                  {p.footer ? <footer className="ui-panel-foot">{p.footer}</footer> : null}
                </motion.div>
              </Dialog.Content>
            </div>
          </Dialog.Portal>
        ) : null}
      </AnimatePresence>
    </Dialog.Root>
  );
}

/**
 * Panneau latéral droit (Radix Dialog) : piège de focus, Échap, clic extérieur, focus rendu au déclencheur,
 * défilement du fond bloqué. Remplace l'ouverture inline des formulaires (QuickForm) : le formulaire va
 * dans `children`, ses boutons dans `footer` (`<button form="id">` si le `<form>` est dans le corps).
 */
export function Sheet(props: SheetProps) {
  return <SheetBase variant="sheet" {...props} />;
}

/** Variante modale centrée (confirmation, saisie courte) — mêmes props que `Sheet`. */
export function Modal(props: SheetProps) {
  return <SheetBase variant="modal" {...props} />;
}

/** Bouton qui ferme le panneau courant (à mettre dans `footer`) : `<SheetClose><button className="btn">Annuler</button></SheetClose>`. */
export function SheetClose({ children }: { children: ReactElement }) {
  return <Dialog.Close asChild>{children}</Dialog.Close>;
}
