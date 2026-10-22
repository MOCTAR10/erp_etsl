import { createColumnHelper, createSortedRowModel, functionalUpdate, rowSortingFeature, tableFeatures, useTable } from "@tanstack/react-table";
import type { SortingState, Updater } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown, Inbox } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMemo, useRef } from "react";
import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { usePagedList } from "../../lib/usePagedList";
import type { Column } from "./DataTable";
import { EmptyState } from "./EmptyState";
import { Menu } from "./Menu";
import type { MenuEntry } from "./Menu";
import { Pagination } from "./Pagination";
import { SearchField } from "./SearchField";
import { Skeleton } from "./Skeleton";

/** Valeur de tri d'une cellule (`null`/`undefined` toujours en fin de liste). */
export type SortValue = string | number | Date | boolean | null | undefined;

/**
 * Colonne de `DataGrid` — sur-ensemble de `Column` (DataTable) : un tableau de colonnes existant
 * fonctionne tel quel ; on ajoute `sortValue` pour rendre la colonne triable.
 */
export interface GridColumn<T> extends Column<T> {
  /** Valeur comparée au tri (client). Sa présence rend la colonne triable. */
  sortValue?: (row: T) => SortValue;
  /** Champ DRF de tri côté serveur (`?ordering=`), utilisé par `toOrdering` en mode contrôlé. */
  sortKey?: string;
  /** Force (`true`) ou interdit (`false`) le tri ; par défaut : triable si `sortValue` ou `sortKey`. */
  sortable?: boolean;
  /** Largeur CSS de la colonne (ex. `120`, `"18%"`). */
  width?: number | string;
}

/** Tri courant : clé de colonne + sens. `null` = ordre d'origine. */
export type GridSort = { id: string; desc: boolean } | null;

/** Tri → paramètre DRF `ordering` (`"-montant"`), d'après `sortKey` (ou la clé de colonne). `""` si aucun tri. */
export function toOrdering<T>(sort: GridSort, columns: GridColumn<T>[]): string {
  if (!sort) return "";
  const col = columns.find((c) => c.key === sort.id);
  const field = col?.sortKey ?? sort.id;
  return sort.desc ? `-${field}` : field;
}

export interface GridPagination {
  page: number;
  pageSize: number;
  count: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
}

export interface DataGridProps<T extends { id: string | number }> {
  columns: GridColumn<T>[];
  rows: T[];
  /** Légende lue par les lecteurs d'écran (masquée). */
  caption?: string;
  /** Chargement : squelette si aucune ligne, sinon lignes atténuées (page précédente conservée). */
  loading?: boolean;
  skeletonRows?: number;
  emptyLabel?: string;
  emptyHint?: string;
  emptyIcon?: LucideIcon;
  /** `comfortable` (défaut) ou `compact` (listes longues, écrans de contrôle). */
  density?: "comfortable" | "compact";
  /** En-têtes collants dans une zone défilante de hauteur `maxHeight` (défaut `min(70vh, 760px)` ; `"none"` = pas de limite). */
  maxHeight?: number | string;
  /** Actions d'une ligne : menu « ⋯ » en dernière colonne (entrées vides = pas de menu pour cette ligne). */
  rowActions?: (row: T) => MenuEntry[];
  /** Ligne cliquable (et activable au clavier : Entrée). */
  onRowClick?: (row: T) => void;
  /** Tri initial (mode client). */
  initialSort?: GridSort;
  /** Tri contrôlé (mode serveur) : avec `onSortChange`, le tableau n'ordonne plus lui-même les lignes. */
  sort?: GridSort;
  onSortChange?: (sort: GridSort) => void;
  /** Pagination serveur (composant `Pagination` existant) sous le tableau. */
  pagination?: GridPagination;
}

const features = tableFeatures({ rowSortingFeature, sortedRowModel: createSortedRowModel() });
const helper = createColumnHelper<typeof features, { id: string | number }>();
const NO_ROWS: never[] = [];

function normalizeSortValue(v: SortValue): string | number | undefined {
  if (v === null || v === undefined || v === "") return undefined;
  if (v instanceof Date) return v.getTime();
  if (typeof v === "boolean") return v ? 1 : 0;
  return v;
}

const collator = new Intl.Collator("fr", { numeric: true, sensitivity: "base" });

/** Comparateur croissant : nombres, puis textes (collation française, numérique : « BC-9 » < « BC-10 »). */
function compare(a: string | number, b: string | number): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return collator.compare(String(a), String(b));
}

const isSortable = <T,>(c: GridColumn<T>) => c.sortable ?? Boolean(c.sortValue || c.sortKey);

/**
 * Grille de données (TanStack Table v9) — remplaçant de `DataTable` page par page, même rendu de base
 * (`<table className="table">`, `num` à droite en chiffres tabulaires) + tri par colonne (`aria-sort`),
 * en-têtes collants, densité, colonne d'actions (`Menu`), états vide (`EmptyState`) et chargement (`Skeleton`).
 * `<DataGrid columns={cols} rows={rows} caption="Bons de commande" rowActions={(r) => [...]} />`.
 */
export function DataGrid<T extends { id: string | number }>({
  columns,
  rows,
  caption,
  loading = false,
  skeletonRows = 6,
  emptyLabel,
  emptyHint,
  emptyIcon,
  density = "comfortable",
  maxHeight,
  rowActions,
  onRowClick,
  initialSort = null,
  sort,
  onSortChange,
  pagination,
}: DataGridProps<T>) {
  const { t } = useTranslation();
  const controlled = sort !== undefined && onSortChange !== undefined;

  // Définitions TanStack stables : recalculées seulement si la liste des colonnes triables change
  // (les pages passent souvent un tableau de colonnes recréé à chaque rendu).
  const colsRef = useRef(columns);
  colsRef.current = columns;
  const signature = columns.map((c) => `${c.key}:${isSortable(c) ? 1 : 0}`).join("|");
  const defs = useMemo(
    () =>
      colsRef.current.map((c) =>
        helper.accessor(
          (row) => {
            const col = colsRef.current.find((x) => x.key === c.key);
            return normalizeSortValue(col?.sortValue?.(row as T));
          },
          {
            id: c.key,
            header: c.key,
            enableSorting: isSortable(c),
            sortUndefined: "last",
            sortFn: (ra, rb, id) => compare(ra.getValue(id) as string | number, rb.getValue(id) as string | number),
          },
        ),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [signature],
  );

  const sortingState: SortingState = sort ? [{ id: sort.id, desc: sort.desc }] : [];
  const handleSortingChange = (updater: Updater<SortingState>) => {
    const next = functionalUpdate(updater, sortingState);
    onSortChange?.(next[0] ? { id: next[0].id, desc: next[0].desc } : null);
  };
  const table = useTable({
    features,
    columns: defs,
    data: (rows.length ? rows : NO_ROWS) as { id: string | number }[],
    getRowId: (row) => String(row.id),
    sortDescFirst: false,
    enableMultiSort: false,
    initialState: { sorting: initialSort ? [initialSort] : [] },
    manualSorting: controlled,
    ...(controlled ? { state: { sorting: sortingState }, onSortingChange: handleSortingChange } : {}),
  });

  const byKey = new Map(columns.map((c) => [c.key, c]));
  const headers = table.getHeaderGroups()[0]?.headers ?? [];
  const bodyRows = table.getRowModel().rows;
  const colCount = columns.length + (rowActions ? 1 : 0);
  const height = maxHeight ?? "min(70vh, 760px)";
  const wrapStyle: CSSProperties | undefined = height === "none" ? undefined : { maxHeight: height };
  const showSkeleton = loading && rows.length === 0;

  let body: ReactNode;
  if (showSkeleton) {
    body = Array.from({ length: skeletonRows }, (_, r) => (
      <tr key={`sk-${r}`} className="ui-grid-skeleton" aria-hidden>
        {Array.from({ length: colCount }, (_, c) => (
          <td key={c}>
            <Skeleton style={{ height: 12, width: `${45 + ((r * 7 + c * 13) % 45)}%` }} />
          </td>
        ))}
      </tr>
    ));
  } else if (rows.length === 0) {
    body = (
      <tr className="ui-grid-empty">
        <td colSpan={colCount}>
          <EmptyState icon={emptyIcon ?? Inbox} label={emptyLabel ?? t("common.empty")} hint={emptyHint} />
        </td>
      </tr>
    );
  } else {
    body = bodyRows.map((r) => {
      const row = r.original as T;
      const actions = rowActions ? rowActions(row).filter(Boolean) : [];
      return (
        <tr
          key={r.id}
          className={onRowClick ? "is-clickable" : undefined}
          tabIndex={onRowClick ? 0 : undefined}
          onClick={onRowClick ? () => onRowClick(row) : undefined}
          onKeyDown={
            onRowClick
              ? (e) => {
                  if (e.key === "Enter" && e.target === e.currentTarget) onRowClick(row);
                }
              : undefined
          }
        >
          {columns.map((c) => (
            <td key={c.key} className={c.num ? "num" : undefined}>
              {c.render(row)}
            </td>
          ))}
          {rowActions ? (
            <td className="ui-grid-actions">{actions.length ? <Menu items={actions} label={t("ui.rowActions")} size="sm" /> : null}</td>
          ) : null}
        </tr>
      );
    });
  }

  return (
    <div className="ui-grid-root">
      <div className="table-wrap ui-grid-wrap" style={wrapStyle}>
        <table className={`table ui-grid ui-grid--${density}${loading && !showSkeleton ? " is-loading" : ""}`} aria-busy={loading || undefined}>
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr>
              {headers.map((h) => {
                const c = byKey.get(h.column.id);
                if (!c) return null;
                const canSort = h.column.getCanSort();
                const sorted = h.column.getIsSorted();
                const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ChevronsUpDown;
                return (
                  <th
                    key={h.id}
                    scope="col"
                    className={[c.num ? "num" : "", canSort ? "sortable" : "", sorted ? "is-sorted" : ""].filter(Boolean).join(" ") || undefined}
                    style={c.width !== undefined ? { width: c.width } : undefined}
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : canSort ? "none" : undefined}
                  >
                    {canSort ? (
                      <button type="button" className="ui-grid-sort" onClick={h.column.getToggleSortingHandler()}>
                        <span>{c.header}</span>
                        <Icon size={13} className="ui-grid-sort-icon" aria-hidden />
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
              {rowActions ? (
                <th scope="col" className="ui-grid-actions">
                  <span className="sr-only">{t("ui.actions")}</span>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
        {showSkeleton ? <span className="sr-only" role="status">{t("ui.loadingRows")}</span> : null}
      </div>
      {pagination ? <Pagination {...pagination} /> : null}
    </div>
  );
}

/**
 * Liste serveur (`usePagedList`) en grille : recherche (si `searchPlaceholder`), grille, pagination — remplaçant
 * direct de `PagedDataTable` (mêmes props + celles de `DataGrid`). Le tri client ordonne la page chargée.
 */
export function PagedDataGrid<T extends { id: string | number }>({
  list,
  searchPlaceholder,
  ...grid
}: Omit<DataGridProps<T>, "rows" | "pagination" | "loading"> & {
  list: ReturnType<typeof usePagedList<T>>;
  searchPlaceholder?: string;
}) {
  return (
    <>
      {searchPlaceholder ? <SearchField value={list.search} onChange={list.setSearch} placeholder={searchPlaceholder} /> : null}
      <DataGrid
        {...grid}
        rows={list.rows}
        loading={list.query.isFetching}
        pagination={{
          page: list.page,
          pageSize: list.pageSize,
          count: list.count,
          onPageChange: list.setPage,
          onPageSizeChange: list.setPageSize,
        }}
      />
    </>
  );
}
