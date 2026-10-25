import { useAuth } from "../store/auth";
import { listAll, type ListAllOptions } from "../lib/listAll";
import type { Me, Tokens } from "../types";

// BASE_URL = "/" en dev/racine, "/erp_etsl/" sous sous-chemin nginx → préfixe tous les /api.
const API_BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

/** Langue de l'interface transmise à l'API (EX-G-07) : messages standard du serveur dans la même langue. */
function langueApi(): string {
  try {
    return localStorage.getItem("etls.lang") === "en" ? "en" : "fr";
  } catch {
    return "fr";
  }
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function raw<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = useAuth.getState();
  const headers = new Headers(init?.headers);
  if (auth.access) headers.set("Authorization", `Bearer ${auth.access}`);
  headers.set("Accept-Language", langueApi());
  if (init?.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(apiUrl(path), { ...init, headers });

  if (auth.access && (await jetonRefuse(res))) {
    if (auth.refresh) {
      try {
        const refreshed = await refreshToken(auth.refresh);
        useAuth.getState().setAccess(refreshed.access);
        const retry = await fetch(apiUrl(path), {
          ...init,
          headers: new Headers({
            ...Object.fromEntries(headers.entries()),
            Authorization: `Bearer ${refreshed.access}`,
          }),
        });
        if (retry.ok) return (retry.status === 204 ? undefined : await retry.json()) as T;
        if (!(await jetonRefuse(retry))) throw new ApiError(retry.status, await retry.json().catch(() => null));
      } catch (e) {
        if (e instanceof ApiError) throw e;
      }
    }
    // Session non renouvelable (jeton de rafraîchissement expiré ou révoqué) : retour à la connexion, avec un
    // message « session expirée » plutôt qu'une erreur sur chaque écran.
    useAuth.getState().expire();
    throw new ApiError(401, { detail: "session_expiree" });
  }

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const message = (detail as { detail?: unknown } | null)?.detail;
    // Mot de passe changé depuis une autre session : jetons révoqués, retour à la connexion.
    if (typeof message === "string" && /password has been changed/i.test(message)) useAuth.getState().clear();
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/**
 * Jeton d'accès refusé : 401, ou 403 « token_not_valid » (serveur dont la session Django précédait le JWT dans
 * DEFAULT_AUTHENTICATION_CLASSES). Lit une copie de la réponse : le corps reste lisible par l'appelant.
 */
async function jetonRefuse(res: Response): Promise<boolean> {
  if (res.status === 401) return true;
  if (res.status !== 403) return false;
  const corps = (await res.clone().json().catch(() => null)) as { code?: unknown } | null;
  return corps?.code === "token_not_valid";
}

async function postForm<T>(path: string, body: Record<string, string>): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** Dépagination : les listes DRF sont paginées par défaut (count/results). */
async function rawList<T>(path: string): Promise<T[]> {
  const page = await raw<import("../types").Paginated<T>>(path);
  return page.results;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

/** Étape MFA (lot 15b) : le mot de passe d'un rôle sensible ne délivre pas de jetons mais un jeton MFA (5 min). */
export interface MfaChallenge {
  mfa_requis: true;
  mfa_enrolement: boolean;
  mfa_jeton: string;
}

export type LoginResult = { user: Me; tokens: Tokens; mfa?: undefined } | { mfa: MfaChallenge };

export async function login(email: string, password: string): Promise<LoginResult> {
  const res = await postForm<Tokens | MfaChallenge>("/api/users/token/", { email, password });
  if ("mfa_requis" in res) return { mfa: res };
  const user = await authenticatedMe(res.access);
  return { user, tokens: res };
}

export async function mfaEnrolement(jeton: string): Promise<{ secret: string; otpauth_uri: string }> {
  return postForm("/api/users/mfa/enrolement/", { mfa_jeton: jeton });
}

export async function mfaVerification(jeton: string, code: string): Promise<{ user: Me; tokens: Tokens }> {
  const tokens = await postForm<Tokens>("/api/users/mfa/verification/", { mfa_jeton: jeton, code });
  const user = await authenticatedMe(tokens.access);
  return { user, tokens };
}

async function refreshToken(refresh: string): Promise<{ access: string }> {
  return postForm<{ access: string }>("/api/users/token/refresh/", { refresh });
}

async function authenticatedMe(access: string): Promise<Me> {
  const res = await fetch(apiUrl("/api/users/me/"), {
    headers: { Authorization: `Bearer ${access}` },
  });
  if (!res.ok) throw new ApiError(res.status, null);
  return (await res.json()) as Me;
}

/** POST rejouable : la clé `Idempotency-Key` évite tout doublon côté serveur (saisies terrain hors-ligne). */
export const postIdempotent = (path: string, body: unknown, key: string) =>
  raw<unknown>(path, {
    method: "POST",
    body: body instanceof FormData ? body : JSON.stringify(body), // FormData : photo prise hors ligne
    headers: { "Idempotency-Key": key },
  });

export const api = {
  get: <T,>(path: string) => raw<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    raw<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T,>(path: string, body: unknown) => raw<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (path: string) => raw<void>(path, { method: "DELETE" }),
  /** Envoi d'une pièce (multipart, champ `fichier`) : certificat numérisé, BL, bon de sortie signé… */
  upload: <T,>(path: string, fichier: File, champ = "fichier", extra?: Record<string, string>) => {
    const body = new FormData();
    body.append(champ, fichier);
    for (const [k, v] of Object.entries(extra ?? {})) body.append(k, v);
    return raw<T>(path, { method: "POST", body });
  },
  /** Toutes les pages d'une liste (listes de choix des formulaires) : suit `next` jusqu'à `maxPages`. */
  listAll: <T,>(path: string, opts?: ListAllOptions) =>
    listAll<T>((p) => raw<import("../types").Paginated<T>>(p), path, opts),
  /** Recherche rapide (palette Ctrl K) : `?search=` d'une liste DRF, premiers résultats seulement, annulable. */
  rechercher: <T,>(path: string, q: string, signal?: AbortSignal, pageSize = 5) =>
    raw<import("../types").Paginated<T>>(`${path}?search=${encodeURIComponent(q)}&page_size=${pageSize}`, { signal }),
  /** Téléchargement authentifié d'un export (CSV, XLSX, PDF) : le serveur journalise l'export (EX-G-10). */
  download: async (path: string, filename: string) => {
    const res = await fetch(apiUrl(path), {
      headers: { Authorization: `Bearer ${useAuth.getState().access ?? ""}` },
    });
    if (!res.ok) throw new ApiError(res.status, null);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
  me: () => raw<Me>("/api/users/me/"),
  monProfil: () => raw<import("../types").MonProfil>("/api/rh-paie/mon-espace/profil/"),
  mesBulletins: () => rawList<import("../types").MonBulletin>("/api/rh-paie/mon-espace/bulletins/"),
  monBulletin: (id: string) => raw<import("../types").MonBulletin>(`/api/rh-paie/mon-espace/bulletins/${id}/`),
  mesConges: () => rawList<import("../types").MonConge>("/api/rh-paie/mon-espace/conges/"),
  deposerConge: (body: Record<string, unknown>) =>
    raw<import("../types").MonConge>("/api/rh-paie/mon-espace/conges/", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  annulerConge: (id: string) =>
    raw<import("../types").MonConge>(`/api/rh-paie/mon-espace/conges/${id}/annuler/`, { method: "POST" }),
  dashboard: () => raw<import("../types").DashboardData>("/api/reports/dashboard/"),
  /** Registre central des paramètres ETSL (écarts transverses) : liste filtrée et compteur des provisoires. */
  parametresEtsl: (qs = "") => raw<import("../lib/parametres").ParametresEtslListe>(`/api/parametres-etsl/${qs}`),
  parametresEtslResume: () => raw<import("../lib/parametres").ParametresEtslResume>("/api/parametres-etsl/resume/"),
  tasks: () => rawList<import("../types").WorkflowTask>("/api/workflow/tasks/"),
  circuits: () => rawList<import("../types").Circuit>("/api/workflow/circuits/"),
  notifications: () => rawList<import("../types").NotificationItem>("/api/workflow/notifications/"),
  opportunities: () =>
    raw<import("../types").Paginated<import("../types").Opportunity>>("/api/commercial/opportunities/"),
  pipeline: () =>
    raw<import("../types").PipelineStats>("/api/commercial/opportunities/pipeline/"),
  purchaseOrders: (params = "") =>
    raw<import("../types").Paginated<import("../types").PurchaseOrder>>(`/api/achats/orders/${params}`),
  ordres: (params = "") =>
    raw<import("../types").Paginated<import("../types").OrdreFabrication>>(`/api/operations/ordres/${params}`),
  charge: () => raw<import("../types").ChargeStats>("/api/operations/ordres/charge/"),
  situations: (params = "") =>
    raw<import("../types").Paginated<import("../types").SituationTravaux>>(`/api/operations/situations/${params}`),
  equipes: (params = "") =>
    raw<import("../types").Paginated<{ id: string; code: string; label: string }>>(`/api/operations/equipes/${params}`),
  affectations: (params = "") =>
    raw<import("../types").Paginated<import("../types").EquipeAffectation>>(`/api/operations/affectations/${params}`),
  presences: (params = "") =>
    raw<import("../types").Paginated<import("../types").PresenceChantier>>(`/api/operations/presences/${params}`),
  equipements: (params = "") =>
    raw<import("../types").Paginated<import("../types").EquipementParc>>(`/api/logistique/equipements/${params}`),
  locationsGR: (params = "") =>
    raw<import("../types").Paginated<import("../types").LocationGR>>(`/api/logistique/locations/${params}`),
  demandesLog: (params = "") =>
    raw<import("../types").Paginated<import("../types").DemandeMobilisation>>(`/api/logistique/demandes/${params}`),
  parcStats: () => raw<import("../types").ParcStats>("/api/logistique/locations/stats/"),
  depots: (params = "") =>
    raw<import("../types").Paginated<import("../types").Depot>>(`/api/stocks/depots/${params}`),
  lotsStocks: (params = "") =>
    raw<import("../types").Paginated<import("../types").LotMatiere>>(`/api/stocks/lots/${params}`),
  certificats: (params = "") =>
    raw<import("../types").Paginated<import("../types").CertificatMatiere>>(`/api/stocks/certificats/${params}`),
  mouvementsStock: (params = "") =>
    raw<import("../types").Paginated<import("../types").MouvementStock>>(`/api/stocks/mouvements/${params}`),
  quantsStock: (params = "") =>
    raw<import("../types").Paginated<import("../types").StockQuant>>(`/api/stocks/quants/${params}`),
  inventaires: (params = "") =>
    raw<import("../types").Paginated<import("../types").Inventaire>>(`/api/stocks/inventaires/${params}`),
  valorisationsMensuelles: () =>
    raw<import("../types").Paginated<import("../types").ValorisationMensuelle>>(`/api/stocks/valorisations/?page_size=24`),
  plansInventaire: () =>
    raw<import("../types").Paginated<import("../types").PlanInventaireTournant>>(`/api/stocks/plans-inventaire/?page_size=20`),
  valorisation: (depot = "") =>
    raw<import("../types").ValorisationRow[]>(`/api/stocks/quants/valorisation/${depot ? `?depot=${depot}` : ""}`),
  soudeurs: (params = "") =>
    raw<import("../types").Paginated<import("../types").Soudeur>>(`/api/qualite/soudeurs/${params}`),
  qualifications: (params = "") =>
    raw<import("../types").Paginated<import("../types").QualificationSoudeur>>(`/api/qualite/qualifications/${params}`),
  wps: (params = "") =>
    raw<import("../types").Paginated<import("../types").WpsWpqr>>(`/api/qualite/wps/${params}`),
  controlesQualite: (params = "") =>
    raw<import("../types").Paginated<import("../types").ControleQualite>>(`/api/qualite/controles/${params}`),
  pvsControle: (params = "") =>
    raw<import("../types").Paginated<import("../types").PvControle>>(`/api/qualite/pvs/${params}`),
  nonConformites: (params = "") =>
    raw<import("../types").Paginated<import("../types").NonConformite>>(`/api/qualite/non-conformites/${params}`),
  actionsCorrectives: (params = "") =>
    raw<import("../types").Paginated<import("../types").ActionCorrective>>(`/api/qualite/actions-correctives/${params}`),
  hseStats: () => raw<import("../types").HseStats>("/api/hse/incidents/stats/"),
  permis: (params = "") =>
    raw<import("../types").Paginated<import("../types").PermisTravail>>(`/api/hse/permis/${params}`),
  incidents: (params = "") =>
    raw<import("../types").Paginated<import("../types").Incident>>(`/api/hse/incidents/${params}`),
  risquesHse: (params = "") =>
    raw<import("../types").Paginated<import("../types").EvaluationRisque>>(`/api/hse/evaluations-risques/${params}`),
  equipementsAtex: (params = "") =>
    raw<import("../types").Paginated<import("../types").EquipementAtex>>(`/api/hse/equipements-atex/${params}`),
  actionsHse: (params = "") =>
    raw<import("../types").Paginated<import("../types").ActionHse>>(`/api/hse/actions/${params}`),
  formationsHse: (params = "") =>
    raw<import("../types").Paginated<import("../types").FormationSecurite>>(`/api/hse/formations/${params}`),
  episHse: (params = "") =>
    raw<import("../types").Paginated<import("../types").Epi>>(`/api/hse/epis/${params}`),
  bordereauxDechets: (params = "") =>
    raw<import("../types").Paginated<import("../types").BordereauDechet>>(`/api/hse/bordereaux-dechets/${params}`),
  auditsHse: (params = "") =>
    raw<import("../types").Paginated<import("../types").AuditHse>>(`/api/hse/audits/${params}`),
  duerHse: (params = "") =>
    raw<import("../types").Paginated<import("../types").Duer>>(`/api/hse/duer/${params}`),
  plansUrgence: (params = "") =>
    raw<import("../types").Paginated<import("../types").PlanUrgence>>(`/api/hse/plans-urgence/${params}`),
  maintenanceStats: () => raw<import("../types").MaintenanceStats>("/api/maintenance/ordres/stats/"),
  actifs: (params = "") =>
    raw<import("../types").Paginated<import("../types").Actif>>(`/api/maintenance/actifs/${params}`),
  ordresTravail: (params = "") =>
    raw<import("../types").Paginated<import("../types").OrdreTravail>>(`/api/maintenance/ordres/${params}`),
  inspections: (params = "") =>
    raw<import("../types").Paginated<import("../types").Inspection>>(`/api/maintenance/inspections/${params}`),
  rhPaieStats: () => raw<import("../types").RhPaieStats>("/api/rh-paie/employes/stats/"),
  employes: (params = "") =>
    raw<import("../types").Paginated<import("../types").Employe>>(`/api/rh-paie/employes/${params}`),
  contratsRh: (params = "") =>
    raw<import("../types").Paginated<import("../types").ContratTravail>>(`/api/rh-paie/contrats/${params}`),
  qualificationsRh: (params = "") =>
    raw<import("../types").Paginated<import("../types").Qualification>>(`/api/rh-paie/qualifications/${params}`),
  congesRh: (params = "") =>
    raw<import("../types").Paginated<import("../types").DemandeConge>>(`/api/rh-paie/conges/${params}`),
  recrutements: (params = "") =>
    raw<import("../types").Paginated<import("../types").Recrutement>>(`/api/rh-paie/recrutements/${params}`),
  formationsRh: (params = "") =>
    raw<import("../types").Paginated<import("../types").Formation>>(`/api/rh-paie/formations/${params}`),
  sanctions: (params = "") =>
    raw<import("../types").Paginated<import("../types").Sanction>>(`/api/rh-paie/sanctions/${params}`),
  saisiesTemps: (params = "") =>
    raw<import("../types").Paginated<import("../types").SaisieTemps>>(`/api/rh-paie/temps/${params}`),
  bulletinsPaie: (params = "") =>
    raw<import("../types").Paginated<import("../types").BulletinPaie>>(`/api/rh-paie/bulletins/${params}`),
  masseSalariale: (params = "") =>
    raw<import("../types").MasseSalariale>(`/api/rh-paie/bulletins/masse/${params}`),
  comptesBancaires: (params = "") =>
    raw<import("../types").Paginated<import("../types").CompteBancaire>>(`/api/comptabilite/comptes-bancaires/${params}`),
  relevesBancaires: (params = "") =>
    raw<import("../types").Paginated<import("../types").ReleveBancaire>>(`/api/comptabilite/releves/${params}`),
  rapprochements: (params = "") =>
    raw<import("../types").Paginated<import("../types").RapprochementBancaire>>(`/api/comptabilite/rapprochements/${params}`),
  engagements: (params = "") =>
    raw<import("../types").Paginated<import("../types").Engagement>>(`/api/comptabilite/engagements/${params}`),
  paiements: (params = "") =>
    raw<import("../types").Paginated<import("../types").Paiement>>(`/api/comptabilite/paiements/${params}`),
  declarationsTva: (params = "") =>
    raw<import("../types").Paginated<import("../types").DeclarationTva>>(`/api/comptabilite/declarations-tva/${params}`),
  controlesCompta: (params = "") =>
    raw<import("../types").Paginated<import("../types").ControleInterne>>(`/api/comptabilite/controles/${params}`),
  cgBudgets: (params = "") =>
    raw<import("../types").Paginated<import("../types").Budget>>(`/api/controle-gestion/budgets/${params}`),
  cgRevisions: (params = "") =>
    raw<import("../types").Paginated<import("../types").BudgetRevision>>(`/api/controle-gestion/revisions/${params}`),
  cgClotures: (params = "") =>
    raw<import("../types").Paginated<import("../types").ClotureGestion>>(`/api/controle-gestion/clotures/${params}`),
  cgCloturesStats: (params = "") =>
    raw<import("../types").CloturesStats>(`/api/controle-gestion/clotures/stats/${params}`),
  cgMarges: (params = "") =>
    raw<import("../types").MargesResult>(`/api/controle-gestion/marges/${params}`),
  fiscalYears: (params = "") =>
    raw<import("../types").Paginated<import("../types").FiscalYear>>(`/api/accounting/fiscal-years/${params}`),
  courriersJuridique: (params = "") =>
    raw<import("../types").Paginated<import("../types").Courrier>>(`/api/juridique/courriers/${params}`),
  conventionsJuridique: (params = "") =>
    raw<import("../types").Paginated<import("../types").Convention>>(`/api/juridique/conventions/${params}`),
  contentieuxJuridique: (params = "") =>
    raw<import("../types").Paginated<import("../types").Contentieux>>(`/api/juridique/contentieux/${params}`),
  cautionsJuridique: (params = "") =>
    raw<import("../types").Paginated<import("../types").Caution>>(`/api/juridique/cautions/${params}`),
  assurancesJuridique: (params = "") =>
    raw<import("../types").Paginated<import("../types").Assurance>>(`/api/juridique/assurances/${params}`),
  reunionsJuridique: (params = "") =>
    raw<import("../types").Paginated<import("../types").Reunion>>(`/api/juridique/reunions/${params}`),
  dossiersGrJuridique: (params = "") =>
    raw<import("../types").Paginated<import("../types").DossierGlobalRental>>(`/api/juridique/dossiers-gr/${params}`),
  alertesJuridique: () => raw<import("../types").AlertesResult>("/api/juridique/alertes/"),
  juridiqueStats: () => raw<import("../types").JuridiqueStats>("/api/juridique/reunions/stats/"),
  dashboardDirection: () =>
    raw<import("../types").DashboardDirection>("/api/analytics/dashboard/"),
  reportingPetrolier: () =>
    raw<import("../types").ReportingPetrolier>("/api/analytics/petrolier/"),
  tendances: () => raw<import("../types").Tendances>("/api/analytics/tendances/"),
  alertesAgregees: () =>
    raw<import("../types").AlertesAgregees>("/api/analytics/alertes/"),
};