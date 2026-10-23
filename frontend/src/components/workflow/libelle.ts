/**
 * Libellés venant du serveur (circuits, types de documents…) : on retire les références
 * d'exigences (« (RF-ERP-W1) », « (M3) », « (C1) ») — aucune référence de cahier des charges à l'écran.
 */
export function cleanLabel(label: string | null | undefined): string {
  if (!label) return "";
  return label
    .replace(/\s*\((?:RF|H|EX|CDC|RG|CL)-[\w.-]*\)/g, "")
    .replace(/\s*\((?:M|C)\d{1,2}\)/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}
