import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { filtersToQuery, type FilterDef, type FilterValues } from "../components/ui";

/**
 * Filtre multicritère d'une liste (EX-G-09) : critères décrits par `GET <url>filtres/` (libellés traduits côté
 * serveur), valeurs saisies dans `FilterBar`, chaîne `extra` à passer à `usePagedList`.
 */
export function useFiltresListe(url: string) {
  const { i18n } = useTranslation();
  const [criteres, setCriteres] = useState<FilterValues>({});
  const defs =
    useQuery({
      queryKey: ["filtres-liste", url, i18n.language],
      queryFn: () => api.get<{ results: FilterDef[] }>(`${url}filtres/`),
      retry: 0,
    }).data?.results ?? [];
  return { defs, criteres, setCriteres, extra: filtersToQuery(criteres) };
}
