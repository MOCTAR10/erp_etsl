/** Fonction de traduction (forme minimale de `t`, cf. `useTranslation`). */
type T = (key: string, opts?: Record<string, unknown>) => string;

/**
 * Libellé lisible d'un code de rôle (`pdg` → « Président-directeur général ») : dictionnaire
 * `shell.roles.*` (FR/EN). Un code inconnu reste lisible (« chef_projet » → « Chef projet »)
 * plutôt que d'afficher une clé i18n brute.
 */
export function roleLabel(t: T, role: string | null | undefined): string {
  if (!role) return "";
  const lisible = role.replace(/_/g, " ");
  return t(`shell.roles.${role}`, { defaultValue: lisible.charAt(0).toUpperCase() + lisible.slice(1) });
}

/** Initiales d'avatar : « Admin ETSL » → « AE », « rh@etls.local » → « RE ». */
export function initiales(nom: string): string {
  return (nom || "?")
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}
