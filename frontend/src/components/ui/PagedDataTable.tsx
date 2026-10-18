import { Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { usePagedList } from "../../lib/usePagedList";
import { DataTable } from "./DataTable";
import type { Column } from "./DataTable";
import { EmptyState } from "./EmptyState";
import { Pagination } from "./Pagination";
import { SearchField } from "./SearchField";

/** Tableau d'une liste serveur : recherche (si `searchPlaceholder`), tableau, pagination. `list` vient de `usePagedList`. */
export function PagedDataTable<T extends { id: string | number }>({
  list,
  columns,
  caption,
  searchPlaceholder,
}: {
  list: ReturnType<typeof usePagedList<T>>;
  columns: Column<T>[];
  caption?: string;
  searchPlaceholder?: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      {searchPlaceholder ? <SearchField value={list.search} onChange={list.setSearch} placeholder={searchPlaceholder} /> : null}
      {list.rows.length === 0 ? (
        <EmptyState icon={Inbox} label={t("common.empty")} />
      ) : (
        <DataTable rows={list.rows} columns={columns} caption={caption} />
      )}
      <Pagination
        page={list.page}
        pageSize={list.pageSize}
        count={list.count}
        onPageChange={list.setPage}
        onPageSizeChange={list.setPageSize}
      />
    </>
  );
}
