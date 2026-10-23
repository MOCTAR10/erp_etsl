import * as Dialog from "@radix-ui/react-dialog";
import { Command, defaultFilter } from "cmdk";
import { CornerDownLeft, Loader2, Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export interface CommandItemDef {
  /** Identifiant unique (toutes listes confondues). */
  id: string;
  label: string;
  icon?: LucideIcon;
  /** Texte secondaire à droite du libellé (chemin, référence, module). */
  hint?: string;
  /** Raccourci affiché (indicatif), ex. « G D ». */
  shortcut?: string;
  /** Termes supplémentaires pris en compte par la recherche (synonymes, chemin, code). */
  keywords?: string[];
  onSelect?: () => void;
  disabled?: boolean;
}

export interface CommandGroupDef {
  id?: string;
  heading: string;
  items: CommandItemDef[];
}

export interface CommandPaletteProps {
  /** Ouverture contrôlée ; sinon état interne (ouvert par Ctrl/⌘+K). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Entrées statiques (pages, actions) — filtrées localement, recherche floue sans accents. */
  groups: CommandGroupDef[];
  /** Appelé après `item.onSelect`, palette déjà fermée (navigation centralisée, télémétrie). */
  onSelect?: (item: CommandItemDef) => void;
  /**
   * Mode « recherche asynchrone » : appelé (avec délai `debounce`) dès `minQuery` caractères ; les groupes
   * renvoyés s'affichent AU-DESSUS des entrées statiques, sans refiltrage local (le serveur a déjà filtré).
   * Le `signal` est annulé si la saisie change avant la réponse.
   */
  search?: (query: string, signal: AbortSignal) => Promise<CommandGroupDef[]>;
  debounce?: number;
  minQuery?: number;
  /** Raccourci global Ctrl/⌘+K (défaut `true`). */
  hotkey?: boolean;
  placeholder?: string;
  emptyLabel?: string;
  /** Nom accessible de la boîte de dialogue. */
  label?: string;
}

/**
 * Score minimal d'une correspondance floue locale (cmdk / command-score) : un saut de caractères au milieu
 * d'un mot vaut ~0,17 ; deux sauts (~0,03) ne sont plus une correspondance crédible et sont masqués.
 */
export const MIN_FUZZY_SCORE = 0.1;
/** Score des entités trouvées par le serveur : toujours au-dessus des entrées locales (max 1). */
const REMOTE_SCORE = 2;

/** Casse + accents : « comptabilite » trouve « Comptabilité ». */
export function normalizeSearch(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/**
 * Palette de commandes générique (cmdk + Radix Dialog) : Ctrl/⌘+K, groupes, recherche floue, icônes et
 * raccourcis, navigation 100 % clavier (↑ ↓ Entrée Échap). Les entrées doivent être déjà filtrées par rôle
 * par l'appelant (RF-59) : la palette n'ajoute aucun accès.
 * `<CommandPalette groups={[{ heading: "Pages", items: [{ id: "nav-/", label: "Tableau de bord", icon: Home, onSelect: () => navigate("/") }] }]} />`
 */
export function CommandPalette({
  open: openProp,
  onOpenChange,
  groups,
  onSelect,
  search,
  debounce = 250,
  minQuery = 2,
  hotkey = true,
  placeholder,
  emptyLabel,
  label,
}: CommandPaletteProps) {
  const { t } = useTranslation();
  const [inner, setInner] = useState(false);
  const open = openProp ?? inner;
  const setOpen = useCallback(
    (v: boolean) => {
      if (openProp === undefined) setInner(v);
      onOpenChange?.(v);
    },
    [openProp, onOpenChange],
  );
  const [query, setQuery] = useState("");
  const [remote, setRemote] = useState<CommandGroupDef[]>([]);
  const [loading, setLoading] = useState(false);

  // Ctrl/⌘+K : bascule l'ouverture depuis n'importe quel écran.
  const openRef = useRef(open);
  openRef.current = open;
  useEffect(() => {
    if (!hotkey) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!openRef.current);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hotkey, setOpen]);

  useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  // Recherche asynchrone (debounce + annulation).
  useEffect(() => {
    const q = query.trim();
    if (!search || !open || q.length < minQuery) {
      setRemote([]);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      search(q, ctrl.signal)
        .then((res) => {
          if (!ctrl.signal.aborted) setRemote(res);
        })
        .catch(() => {
          if (!ctrl.signal.aborted) setRemote([]);
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setLoading(false);
        });
    }, debounce);
    return () => {
      ctrl.abort();
      window.clearTimeout(timer);
    };
  }, [query, open, search, debounce, minQuery]);

  // Filtre : libellé + mots-clés normalisés (la `value` cmdk est l'identifiant, pas le texte).
  const index = useMemo(() => {
    const m = new Map<string, string>();
    for (const g of groups) for (const it of g.items) m.set(it.id, normalizeSearch(it.label));
    return m;
  }, [groups]);
  // Entités serveur (déjà filtrées côté API) : en tête de liste, jamais masquées par le seuil flou.
  // Lu par référence : cmdk peut noter un élément au montage, avant la mise à jour de ses props.
  const remoteIds = useRef<Set<string>>(new Set());
  remoteIds.current = new Set(remote.flatMap((g) => g.items.map((it) => it.id)));
  const filter = useCallback(
    (value: string, q: string, keywords?: string[]) => {
      if (remoteIds.current.has(value)) return REMOTE_SCORE;
      const score = defaultFilter(index.get(value) ?? normalizeSearch(value), normalizeSearch(q), keywords?.map(normalizeSearch));
      return score >= MIN_FUZZY_SCORE ? score : 0;
    },
    [index],
  );

  const choose = (item: CommandItemDef) => {
    setOpen(false);
    item.onSelect?.();
    onSelect?.(item);
  };

  const renderItem = (item: CommandItemDef, forceMount = false) => {
    const Icon = item.icon;
    return (
      <Command.Item
        key={item.id}
        value={item.id}
        keywords={item.keywords}
        disabled={item.disabled}
        forceMount={forceMount}
        onSelect={() => choose(item)}
        className="ui-cmd-item"
      >
        <span className="ui-cmd-icon" aria-hidden>
          {Icon ? <Icon size={16} /> : null}
        </span>
        <span className="ui-cmd-label">{item.label}</span>
        {item.hint ? <span className="ui-cmd-hint">{item.hint}</span> : null}
        {item.shortcut ? <kbd className="ui-kbd">{item.shortcut}</kbd> : null}
        <CornerDownLeft size={14} className="ui-cmd-enter" aria-hidden />
      </Command.Item>
    );
  };

  const name = label ?? t("ui.command.label");
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="ui-overlay ui-cmd-overlay" />
        <Dialog.Content className="ui-cmd" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">{name}</Dialog.Title>
          <Command label={name} filter={filter} loop>
            <div className="ui-cmd-search">
              <Search size={17} aria-hidden />
              <Command.Input value={query} onValueChange={setQuery} placeholder={placeholder ?? t("ui.command.placeholder")} />
              {loading ? <Loader2 size={16} className="ui-spin ui-cmd-spinner" aria-hidden /> : null}
              <kbd className="ui-kbd">{t("ui.command.esc")}</kbd>
            </div>
            <Command.List className="ui-cmd-list">
              {loading ? <Command.Loading label={t("ui.command.loading")}>{null}</Command.Loading> : null}
              {!loading && !remote.some((g) => g.items.length) ? <Command.Empty className="ui-cmd-empty">{emptyLabel ?? t("ui.command.empty")}</Command.Empty> : null}
              {remote.map((g, gi) =>
                g.items.length ? (
                  <Command.Group key={g.id ?? `r-${gi}`} heading={g.heading} forceMount className="ui-cmd-group">
                    {g.items.map((it) => renderItem(it, true))}
                  </Command.Group>
                ) : null,
              )}
              {groups.map((g, gi) =>
                g.items.length ? (
                  <Command.Group key={g.id ?? `g-${gi}`} heading={g.heading} className="ui-cmd-group">
                    {g.items.map((it) => renderItem(it))}
                  </Command.Group>
                ) : null,
              )}
            </Command.List>
            <div className="ui-cmd-foot" aria-hidden>
              {t("ui.command.hint")}
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
