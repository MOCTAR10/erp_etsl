import type { Paginated } from "../types";

export interface ListAllOptions {
  /** Taille de page demandée (le serveur plafonne à 500). */
  pageSize?: number;
  /** Plafond de pages suivies : garde-fou contre une liste démesurée. */
  maxPages?: number;
}

/** Ajoute (ou remplace) des paramètres de requête sur un chemin d'API, avec ou sans `?` existant. */
function withParams(path: string, params: Record<string, number>): string {
  const [base, query = ""] = path.split("?");
  const qs = new URLSearchParams(query);
  for (const [k, v] of Object.entries(params)) qs.set(k, String(v));
  return `${base}?${qs.toString()}`;
}

/**
 * Récupère toutes les pages d'une liste DRF (liste de choix d'un formulaire) en suivant `next`
 * jusqu'à `maxPages`. Les appels qui veulent une seule page continuent d'utiliser `api.get`.
 */
export async function listAll<T>(
  fetchPage: (path: string) => Promise<Paginated<T>>,
  path: string,
  { pageSize = 500, maxPages = 10 }: ListAllOptions = {},
): Promise<T[]> {
  const out: T[] = [];
  for (let page = 1; page <= maxPages; page++) {
    const res = await fetchPage(withParams(path, { page_size: pageSize, page }));
    out.push(...res.results);
    if (!res.next) break;
  }
  return out;
}
