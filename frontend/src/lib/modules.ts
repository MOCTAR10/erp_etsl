/**
 * Rattachement route SPA <-> application ERP, et rôle -> modules lisibles.
 *
 * Source de vérité côté Django : `backend/users/rbac.py` (`ERP_APPS:24-37`,
 * `ROLE_MODULES:55-136`). Les libellés i18n sont ceux de la sidebar (`nav.*`)
 * pour éviter un second jeu de libellés à traduire.
 *
 * `ROUTE_APP` est en `as const` : une route oubliée ou mal orthographiée dans
 * `MODULE_NAV` devient une erreur de compilation, pas un lien menu mort.
 */

/** Route de la sidebar -> application ERP. */
export const ROUTE_APP = {
  "/pipeline": "commercial",
  "/purchases": "achats",
  "/operations": "operations",
  "/logistique": "logistique",
  "/stocks": "stocks",
  "/qualite": "qualite",
  "/hse": "hse",
  "/maintenance": "maintenance",
  "/rh-paie": "rh_paie",
  "/comptabilite": "comptabilite",
  "/controle-gestion": "controle_gestion",
  "/juridique": "juridique",
} as const;

/** Libellé d'une application ERP, union dérivée de `ROUTE_APP`. */
export type ErpApp = (typeof ROUTE_APP)[keyof typeof ROUTE_APP];

/** Application ERP -> clé i18n de la sidebar. `Record` exhaustif : TS exige les 12. */
export const APP_NAV_KEY: Record<ErpApp, string> = {
  commercial: "nav.pipeline",
  achats: "nav.purchases",
  operations: "nav.operations",
  logistique: "nav.logistique",
  stocks: "nav.stocks",
  qualite: "nav.qualite",
  hse: "nav.hse",
  maintenance: "nav.maintenance",
  rh_paie: "nav.rhPaie",
  comptabilite: "nav.comptabilite",
  controle_gestion: "nav.controleGestion",
  juridique: "nav.juridique",
};

/**
 * Un module est visible si le rôle le lit. **Fail-open** : une session
 * persistée avant l'introduction de `modules` (zustand `etls.auth`) n'a pas le
 * champ, et on ne masque alors rien — le 403 du backend reste la garde finale.
 */
export function canSeeApp(modules: string[] | undefined, app: string): boolean {
  if (!modules) return true;
  return modules.includes(app);
}

/** Application ERP servie par une route de module. */
export function appForRoute(to: string): ErpApp | undefined {
  return (ROUTE_APP as Record<string, ErpApp>)[to];
}
