import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";

export interface Option {
  value: string;
  label: string;
}

/**
 * Liste de choix d'un formulaire de saisie Achats : toutes les pages de la référence (`api.listAll`), libellé
 * dérivé de la ligne. Un échec de chargement laisse la liste vide (le serveur reste seul juge à l'envoi).
 */
export function useRefOptions<T extends { id: string }>(key: string, path: string, label: (r: T) => string): Option[] {
  const q = useQuery({ queryKey: ["achats-ref", key, path], queryFn: () => api.listAll<T>(path), retry: 0 });
  return (q.data ?? []).map((r) => ({ value: r.id, label: label(r) }));
}

export interface Analytique {
  id: string;
  axis_code: string;
  code: string;
  label: string;
}

export const useAnalytiques = () =>
  useRefOptions<Analytique>("analytiques", "/api/referentiels/analytic-accounts/", (a) => `${a.axis_code} · ${a.code} — ${a.label}`);
