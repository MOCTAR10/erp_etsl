/**
 * Registre central des paramètres ETSL (écarts transverses) : types servis par `GET /api/parametres-etsl/` et
 * construction de l'appel d'édition vers l'endpoint EXISTANT de l'application (droits du module, inchangés).
 */

export interface EditionParametre {
  method: "PATCH" | "POST";
  path: string;
  champ: string;
  extra: Record<string, string>;
}

export interface ParametreEtsl {
  id: string;
  module: string;
  module_label: string;
  modele: string;
  code: string;
  label: string;
  groupe: string;
  valeur: string;
  unite: string;
  type_valeur: "decimal" | "entier" | "json" | "texte";
  provisoire: boolean;
  confirme_le: string | null;
  confirme_par: string | null;
  edition: EditionParametre;
  confirmation: string;
  ecran: string;
}

export interface ParametresEtslListe {
  count: number;
  provisoires: number;
  modules: { module: string; label: string }[];
  results: ParametreEtsl[];
}

export interface ParametresEtslResume {
  total: number;
  provisoires: number;
  par_module: { module: string; label: string; total: number; provisoires: number }[];
}

/** Erreur de saisie détectée avant l'appel (évite un aller-retour serveur pour une valeur manifestement invalide). */
export class SaisieInvalide extends Error {}

/** Corps de la requête d'édition : `{ <champ>: valeur, ...extra }` ; JSON analysé, nombres normalisés (virgule). */
export function corpsEdition(p: ParametreEtsl, saisie: string): Record<string, unknown> {
  const brut = saisie.trim();
  let valeur: unknown = brut;
  if (p.type_valeur === "json") {
    try {
      valeur = JSON.parse(brut);
    } catch {
      throw new SaisieInvalide("JSON");
    }
  } else if (p.type_valeur === "decimal" || p.type_valeur === "entier") {
    const normalise = brut.replace(/\s/g, "").replace(",", ".");
    if (normalise === "" || Number.isNaN(Number(normalise))) throw new SaisieInvalide("nombre");
    if (p.type_valeur === "entier" && !Number.isInteger(Number(normalise))) throw new SaisieInvalide("entier");
    valeur = normalise;
  } else if (!brut) {
    throw new SaisieInvalide("texte");
  }
  return { ...p.edition.extra, [p.edition.champ]: valeur };
}

/** Lignes regroupées par module, dans l'ordre servi par l'API. */
export function parModule(rows: ParametreEtsl[]): { module: string; label: string; rows: ParametreEtsl[] }[] {
  const out: { module: string; label: string; rows: ParametreEtsl[] }[] = [];
  for (const r of rows) {
    let g = out.find((x) => x.module === r.module);
    if (!g) {
      g = { module: r.module, label: r.module_label, rows: [] };
      out.push(g);
    }
    g.rows.push(r);
  }
  return out;
}
