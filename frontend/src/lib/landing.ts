export const DEFAULT_LANDING = "/";

const LANDING_BY_ROLE: Record<string, string> = {
  // Pilotage / gouvernance : le tableau de bord reste la vue par défaut.
  // `admin` doit rester sur `/` : `auth.spec.ts` et `e2e/helpers.ts` le
  // vérifient (« connecte l'admin et atterrit sur le tableau de bord »).
  admin: "/",
  pdg: "/",
  dga: "/",
  direction: "/",
  chef_service: "/",

  // Encadrement
  secretaire_general: "/circuits",
  directeur_projets: "/kanban",
  directeur_operations: "/operations",

  // Métiers : on arrive sur le module qui porte le métier du rôle.
  rh: "/rh-paie",
  finance: "/comptabilite",
  comptable: "/comptabilite",
  qaqc: "/qualite",
  hse: "/hse",
  logistique: "/logistique",
  maintenance: "/maintenance",
  chef_atelier: "/operations",
  // Consommateurs de la Couche D (écarts a4).
  charge_affaires: "/pipeline",
  controleur_gestion: "/controle-gestion",
};

export function landingForRole(role: string | null | undefined): string {
  if (!role) return DEFAULT_LANDING;
  return LANDING_BY_ROLE[role] ?? DEFAULT_LANDING;
}
