import { useState } from "react";
import i18n from "i18next";

/**
 * Pagination côté client d'une liste déjà chargée (tableaux longs de l'écran Opérations) : tranche de lignes +
 * objet `pagination` au format de `DataTable` / `DataGrid` (même composant `Pagination` que les listes serveur).
 */
export function useClientPage<T>(rows: T[], initialSize = 20) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialSize);
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pages);
  return {
    rows: rows.slice((current - 1) * pageSize, current * pageSize),
    pagination: {
      page: current,
      pageSize,
      count: rows.length,
      onPageChange: setPage,
      onPageSizeChange: (size: number) => {
        setPageSize(size);
        setPage(1);
      },
    },
  };
}

/**
 * Libellé traduit d'un statut (code de l'API) : `revueR2.operations.statut.<famille>.<code>`, à défaut le libellé
 * fourni par le serveur (toujours en français) — jamais le code brut.
 */
export function statutLabel(famille: string, code: string, fallback: string): string {
  const key = `revueR2.operations.statut.${famille}.${code}`;
  return i18n.exists(key) ? String(i18n.t(key)) : fallback || code;
}

/** Nombre de décimales significatives d'une valeur décimale DRF (« 5.50 » → 1, « 12.00 » → 0), plafonné à 3. */
export const decimales = (v: string) => {
  const frac = (v.split(".")[1] ?? "").replace(/0+$/, "");
  return Math.min(frac.length, 3);
};

/** Style d'une cellule qui ne doit pas passer à la ligne (codes, périodes, boutons d'action). */
export const NOWRAP = { whiteSpace: "nowrap" } as const;
