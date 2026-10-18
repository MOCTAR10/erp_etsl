import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import type { Paginated } from "../types";

/** Construit la query string `?page=&page_size=&search=` (+ filtres fixes déjà au format `a=b&c=d`). */
export function pagedQuery(page: number, pageSize: number, search: string, extra = ""): string {
  const qs = new URLSearchParams(extra);
  qs.set("page", String(page));
  qs.set("page_size", String(pageSize));
  if (search.trim()) qs.set("search", search.trim());
  return `?${qs.toString()}`;
}

/**
 * Liste paginée côté serveur avec recherche : page, taille et texte sont l'état ; la clé de requête les porte
 * (TanStack Query), l'ancienne page reste affichée pendant le chargement de la suivante.
 */
export function usePagedList<T>(
  key: string,
  fetcher: (query: string) => Promise<Paginated<T>>,
  { pageSize: initialSize = 20, extra = "", enabled = true }: { pageSize?: number; extra?: string; enabled?: boolean } = {},
) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeState] = useState(initialSize);
  const [search, setSearchState] = useState("");

  const query = useQuery({
    queryKey: [key, page, pageSize, search, extra],
    queryFn: () => fetcher(pagedQuery(page, pageSize, search, extra)),
    placeholderData: keepPreviousData,
    enabled,
  });

  const setSearch = useCallback((value: string) => {
    setSearchState(value);
    setPage(1);
  }, []);
  const setPageSize = useCallback((size: number) => {
    setPageSizeState(size);
    setPage(1);
  }, []);

  return {
    query,
    rows: query.data?.results ?? [],
    count: query.data?.count ?? 0,
    page,
    pageSize,
    search,
    setPage,
    setPageSize,
    setSearch,
  };
}
