import { PagedDataGrid } from "./DataGrid";

/**
 * Tableau d'une liste serveur : recherche (si `searchPlaceholder`), tableau, pagination — adaptateur vers
 * `PagedDataGrid` (mêmes props, plus celles de `DataGrid`). `list` vient de `usePagedList`.
 */
export const PagedDataTable = PagedDataGrid;
