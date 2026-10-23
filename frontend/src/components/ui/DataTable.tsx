import type { ReactNode } from "react";

import type { ActionDef } from "./ActionBar";
import { CardActions } from "./Board";
import { DataGrid } from "./DataGrid";
import type { DataGridProps, SortValue } from "./DataGrid";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** Colonne numérique : alignée à droite, chiffres tabulaires. */
  num?: boolean;
  /** Tri (voir `GridColumn`) : valeur comparée côté client ; sa présence rend la colonne triable. */
  sortValue?: (row: T) => SortValue;
  sortKey?: string;
  sortable?: boolean;
  width?: number | string;
}

/**
 * Tableau de données dense (listes d'entités) — désormais un adaptateur vers `DataGrid` (même rendu
 * `.table`, en-têtes en casse de phrase, état vide dessiné). Les props historiques (`columns`, `rows`,
 * `caption`) sont inchangées ; toutes celles de `DataGrid` sont acceptées en plus (`rowActions`, `sortValue`…).
 * Sans `maxHeight`, le tableau suit la hauteur de la page (pas de défilement imbriqué).
 */
export function DataTable<T extends { id: string | number }>({ maxHeight = "none", ...props }: DataGridProps<T>) {
  return <DataGrid maxHeight={maxHeight} {...props} />;
}

/**
 * Colonne d'actions de ligne (dernière colonne, alignée à droite) : une action principale en bouton compact,
 * les autres dans le menu « ⋯ » — mêmes `ActionDef` que `ActionBar`. Libellé d'en-tête lu par les lecteurs d'écran.
 */
export function actionsColumn<T>(label: string, actions: (row: T) => ActionDef[], primary?: (row: T) => string | undefined): Column<T> {
  return {
    key: "__actions",
    header: <span className="sr-only">{label}</span>,
    render: (row) => <CardActions actions={actions(row)} primary={primary?.(row)} align="end" />,
  };
}
