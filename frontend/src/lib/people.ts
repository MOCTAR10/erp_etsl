/**
 * Nom affichable d'une personne — **jamais l'e-mail** (constats A-03 / A-24 / B17).
 *
 * API (à copier telle quelle par les autres écrans) :
 *
 *   import { displayName, personInitials } from "../lib/people";
 *   const { t } = useTranslation();
 *   displayName(t, user)        // « Awa Ndong » | « Secrétaire général » | « Utilisateur »
 *   personInitials(t, user)     // « AN » | « SG »
 *
 * `user` est n'importe quel objet « personne » (`PersonLike`) : champs facultatifs, plusieurs
 * conventions de nommage du backend acceptées.
 *
 * Ordre de repli :
 *   1. nom complet déjà composé par le backend (`full_name`, `name`, `*_name` passé en `name`) ;
 *   2. prénom + nom (`first_name` + `last_name`) ;
 *   3. libellé du rôle via i18n `shell.roles.*` (`roleLabel`) ;
 *   4. libellé générique i18n `premiumPilotage.people.unknown` (« Utilisateur »).
 *
 * Un « nom » qui ressemble à un e-mail (contient « @ ») est ignoré : l'e-mail n'est donc jamais
 * affiché comme nom. Pour le garder accessible, le mettre en `title` (cf. `personTitle`).
 */
import { initiales, roleLabel } from "./roles";

/** Fonction de traduction (forme minimale de `t`, cf. `useTranslation`). */
type T = (key: string, opts?: Record<string, unknown>) => string;

export interface PersonLike {
  full_name?: string | null;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
  email?: string | null;
}

const clean = (v: string | null | undefined): string => {
  const s = (v ?? "").trim();
  return s && !s.includes("@") ? s : "";
};

/** Nom complet (ou libellé de rôle) d'une personne, jamais son e-mail. */
export function displayName(t: T, person: PersonLike | null | undefined): string {
  if (!person) return t("premiumPilotage.people.unknown");
  const direct = clean(person.full_name) || clean(person.name);
  if (direct) return direct;
  const composed = [clean(person.first_name), clean(person.last_name)].filter(Boolean).join(" ");
  if (composed) return composed;
  if (person.role) return roleLabel(t, person.role);
  return t("premiumPilotage.people.unknown");
}

/** Initiales d'avatar dérivées du nom affichable (jamais de l'e-mail). */
export function personInitials(t: T, person: PersonLike | null | undefined): string {
  return initiales(displayName(t, person));
}

/** Infobulle : nom affichable + e-mail (l'e-mail n'apparaît qu'ici). */
export function personTitle(t: T, person: PersonLike | null | undefined): string {
  const nom = displayName(t, person);
  const mail = (person?.email ?? "").trim();
  return mail ? `${nom} — ${mail}` : nom;
}

/** Teinte d'avatar stable (0-359) dérivée du nom, pour distinguer deux « CA ». */
export function avatarHue(nom: string): number {
  let h = 0;
  for (let i = 0; i < nom.length; i += 1) h = (h * 31 + nom.charCodeAt(i)) % 360;
  return h;
}
