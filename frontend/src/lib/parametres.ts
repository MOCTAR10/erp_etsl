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
  if (p.edition.champ === "*") {
    // Paramètre composite (gabarit d'import) : chaque clé de l'objet est un champ de l'endpoint.
    if (!valeur || typeof valeur !== "object" || Array.isArray(valeur)) throw new SaisieInvalide("objet JSON");
    return { ...p.edition.extra, ...(valeur as Record<string, unknown>) };
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

/** Unités qui codent un choix (1 / 2 / 3) : la valeur affichée est le libellé de l'option, pas le chiffre. */
export const UNITES_CODEES = new Set(["choix", "code", "niveau", "1/2", "clé", "cle"]);
/** Unités booléennes (0 / 1) : « Oui » / « Non », ou le libellé de l'option décrit dans le libellé du paramètre. */
export const UNITES_BOOLEENNES = new Set(["0/1", "booléen", "booleen", "oui/non"]);
/** Unités qui décrivent le type de saisie (et non une grandeur) : jamais affichées après la valeur. */
export const UNITES_TECHNIQUES = new Set(["texte", "json", "score", "rôles", "roles"]);

/** Unité normalisée (« 0 / 1 » → « 0/1 », casse ignorée). */
export const uniteCle = (unite: string | null | undefined) => (unite ?? "").replace(/\s/g, "").toLowerCase();

const OPTION = /(?:^|[\s(,;:])(\d+)\s*=\s*([^,;()]+(?:\([^)]*\))?[^,;()]*)/g;

/**
 * Options d'un paramètre codé, décrites dans son libellé :
 * « Méthode (1 = coûts engagés / budget, 2 = situations de travaux) » → { "1": "coûts engagés / budget", "2": "situations de travaux" }.
 */
export function optionsCodees(label: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of label.matchAll(OPTION)) {
    const texte = m[2].trim();
    if (texte) out[m[1]] = texte;
  }
  return out;
}

/** Libellé de l'option correspondant à la valeur (« 2.00 » → « situations de travaux »), majuscule initiale ; null sinon. */
export function optionPourValeur(label: string, valeur: string): string | null {
  const n = Number(valeur);
  if (!Number.isFinite(n) || !Number.isInteger(n)) return null;
  const texte = optionsCodees(label)[String(n)];
  return texte ? texte.charAt(0).toUpperCase() + texte.slice(1) : null;
}

/**
 * Libellé court : la liste des options codées (« (1 = …, 2 = …) » ou « : 1 = …, 0 = … ») sort du libellé, puisque la
 * valeur affiche déjà l'option retenue. Le libellé complet reste disponible (infobulle, panneau d'édition).
 */
export function libelleCourt(label: string): string {
  const paren = label.search(/\s*\((?=[^()]*\d+\s*=)/);
  if (paren > 0) {
    const court = label.slice(0, paren).trim();
    if (court) return court;
  }
  const deuxPoints = label.search(/\s*:\s*\d+\s*=/);
  if (deuxPoints > 0) return label.slice(0, deuxPoints).trim();
  return label;
}
