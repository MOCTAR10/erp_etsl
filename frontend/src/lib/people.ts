/**
 * Nom d'une personne affiché dans l'interface : jamais une adresse e-mail technique.
 * - objet utilisateur : « Prénom Nom » (`full_name`, `nom_complet`, `name` ou `first_name` + `last_name`) ;
 * - chaîne : renvoyée telle quelle, sauf si c'est une adresse e-mail (le serveur se rabat sur l'e-mail
 *   quand le compte n'a ni prénom ni nom) → partie locale lisible : « demo.logistique@etls.local » → « Logistique »,
 *   « jean-paul.mba@etsl.ga » → « Jean-Paul Mba », « demo.rh@etls.local » → « RH » ;
 * - absent → `fallback` (« — » par défaut).
 */
export interface PersonLike {
  full_name?: string | null;
  nom_complet?: string | null;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
}

/** Segments techniques des comptes de démonstration ou de test, jamais montrés comme nom. */
const TECHNIQUES = new Set(["demo", "test", "e2e", "noreply", "no-reply"]);

const majuscule = (s: string) => s.charAt(0).toLocaleUpperCase("fr") + s.slice(1).toLocaleLowerCase("fr");

/** « jean-paul.mba » → « Jean-Paul Mba » (segments techniques retirés). */
function nomDepuisEmail(email: string): string {
  const local = email.split("@")[0] ?? "";
  const segments = local
    .split(/[._+]+/)
    .map((s) => s.trim())
    .filter((s) => s && !TECHNIQUES.has(s.toLowerCase()) && !/^\d+$/.test(s));
  if (segments.length === 0) return local;
  // Compte de service à segment unique court (« rh », « dsi ») : sigle en capitales.
  if (segments.length === 1 && segments[0].length <= 3) return segments[0].toLocaleUpperCase("fr");
  return segments.map((s) => s.split("-").map(majuscule).join("-")).join(" ");
}

export const isEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());

export function displayName(person: PersonLike | string | null | undefined, fallback = "—"): string {
  if (person === null || person === undefined) return fallback;
  if (typeof person === "string") {
    const s = person.trim();
    if (!s) return fallback;
    return isEmail(s) ? nomDepuisEmail(s) : s;
  }
  const complet =
    person.full_name?.trim() ||
    person.nom_complet?.trim() ||
    person.name?.trim() ||
    [person.first_name, person.last_name].filter((x) => x && x.trim()).join(" ").trim();
  if (complet) return isEmail(complet) ? nomDepuisEmail(complet) : complet;
  return person.email ? nomDepuisEmail(person.email) : fallback;
}
