import { useAuth } from "../store/auth";
import type { Me, Tokens } from "../types";

async function raw<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = useAuth.getState();
  const headers = new Headers(init?.headers);
  if (auth.access) headers.set("Authorization", `Bearer ${auth.access}`);
  if (init?.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(path, { ...init, headers });

  if (res.status === 401 && auth.refresh) {
    try {
      const refreshed = await refreshToken(auth.refresh);
      useAuth.getState().setAccess(refreshed.access);
      const retry = await fetch(path, {
        ...init,
        headers: new Headers({
          ...Object.fromEntries(headers.entries()),
          Authorization: `Bearer ${refreshed.access}`,
        }),
      });
      if (retry.ok) return (await retry.json()) as T;
    } catch {
      useAuth.getState().clear();
    }
  }

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postForm<T>(path: string, body: Record<string, string>): Promise<T> {
  const res = await fetch(path, {
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

export async function login(email: string, password: string): Promise<{ user: Me; tokens: Tokens }> {
  const tokens = await postForm<Tokens>("/api/users/token/", { email, password });
  const user = await authenticatedMe(tokens.access);
  return { user, tokens };
}

async function refreshToken(refresh: string): Promise<{ access: string }> {
  return postForm<{ access: string }>("/api/users/token/refresh/", { refresh });
}

async function authenticatedMe(access: string): Promise<Me> {
  const res = await fetch("/api/users/me/", {
    headers: { Authorization: `Bearer ${access}` },
  });
  if (!res.ok) throw new ApiError(res.status, null);
  return (await res.json()) as Me;
}

export const api = {
  get: <T,>(path: string) => raw<T>(path),
  me: () => raw<Me>("/api/users/me/"),
  dashboard: () => raw<import("../types").DashboardData>("/api/reports/dashboard/"),
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
};