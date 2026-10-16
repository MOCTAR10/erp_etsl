import { AnimatePresence, motion } from "motion/react";
import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";

import { motionTokens } from "../theme/tokens";

export interface PaletteItem {
  id: string;
  label: string;
  group: string;
  Icon: LucideIcon;
  /** Texte additionnel pris en compte par la recherche (chemin, synonymes). */
  keywords?: string;
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  items: PaletteItem[];
  placeholder: string;
  emptyLabel: string;
}

/** Normalise (casse + accents) pour une recherche tolérante : « comptabilite » trouve « Comptabilité ». */
export function normalize(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function filterItems(items: PaletteItem[], query: string): PaletteItem[] {
  const q = normalize(query.trim());
  if (!q) return items;
  return items.filter((it) => normalize(`${it.label} ${it.keywords ?? ""}`).includes(q));
}

/**
 * Palette de commandes (Ctrl/Cmd + K) : navigation entre pages et actions rapides,
 * 100 % clavier (↑ ↓ Entrée Échap). Les entrées sont déjà filtrées par rôle (RF-59)
 * par l'appelant : la palette n'ajoute aucun accès.
 */
export function CommandPalette({ open, onClose, items, placeholder, emptyLabel }: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const results = useMemo(() => filterItems(items, query), [items, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // après le montage de la modale
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [active, results]);

  const choose = (item: PaletteItem | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (results.length ? (i + 1) % results.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (results.length ? (i - 1 + results.length) % results.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  let lastGroup = "";
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="cmdk-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: motionTokens.duration.fast }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            className="cmdk"
            role="dialog"
            aria-modal="true"
            aria-label={placeholder}
            initial={{ opacity: 0, y: -motionTokens.distance.md, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -motionTokens.distance.sm, scale: 0.98 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
            onKeyDown={onKeyDown}
          >
            <div className="cmdk-input">
              <Search size={16} aria-hidden="true" />
              <input
                ref={inputRef}
                type="text"
                role="combobox"
                aria-expanded="true"
                aria-controls="cmdk-list"
                aria-activedescendant={results[active] ? `cmdk-${results[active].id}` : undefined}
                aria-label={placeholder}
                placeholder={placeholder}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              <kbd>Esc</kbd>
            </div>
            <div className="cmdk-list" id="cmdk-list" role="listbox" ref={listRef}>
              {results.length === 0 && <div className="cmdk-empty">{emptyLabel}</div>}
              {results.map((item, i) => {
                const header = item.group !== lastGroup;
                lastGroup = item.group;
                return (
                  <div key={item.id} role="presentation">
                    {header && <div className="cmdk-group">{item.group}</div>}
                    <button
                      type="button"
                      id={`cmdk-${item.id}`}
                      role="option"
                      aria-selected={i === active}
                      className={i === active ? "cmdk-item active" : "cmdk-item"}
                      onMouseMove={() => setActive(i)}
                      onClick={() => choose(item)}
                    >
                      <item.Icon size={16} aria-hidden="true" />
                      <span>{item.label}</span>
                      {i === active && <CornerDownLeft size={14} className="cmdk-enter" aria-hidden="true" />}
                    </button>
                  </div>
                );
              })}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
