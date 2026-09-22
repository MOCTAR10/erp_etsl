export interface Me {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_active: boolean;
}

export interface Tokens {
  access: string;
  refresh: string;
}

export interface KpiDocuments {
  total: number;
  storage_bytes: number;
}
export interface KpiWorkflow {
  pending: number;
  overdue: number;
  avg_processing_days: number | null;
}
export interface KpiRetentionItem {
  id: string;
  titre: string;
  type: string;
  retention_fin: string;
}
export interface DashboardData {
  documents: KpiDocuments & { by_status: Record<string, number>; by_type: Array<{ type__label: string; count: number }> };
  workflow: KpiWorkflow;
  retention: { due_count: number; due: KpiRetentionItem[] };
}

export type TaskStatus = "pending" | "done" | "rejected" | "delegated";

export interface WorkflowTask {
  id: string;
  document: string;
  document_title: string;
  circuit_label: string;
  step_name: string;
  step_order: number;
  assigned_to: string | null;
  assigned_to_email: string | null;
  status: TaskStatus;
  due_date: string;
  completed_at: string | null;
  created_at: string;
  comments_count: number;
}

export interface CircuitStep {
  id: number;
  order: number;
  name: string;
  actor_role_label: string;
  max_days: number;
}
export interface Circuit {
  id: number;
  code: string;
  label: string;
  max_days: number;
  is_active: boolean;
  steps: CircuitStep[];
}

export interface NotificationItem {
  id: string;
  subject: string;
  message: string;
  kind: "reminder" | "escalation" | "info";
  is_read: boolean;
  document_title: string | null;
  step_name: string | null;
  created_at: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type OpportunityStage =
  | "prospection"
  | "qualification"
  | "offre"
  | "negociation"
  | "gagne"
  | "perdu";

export interface Opportunity {
  id: string;
  code: string;
  client: string | null;
  client_name: string | null;
  subject: string;
  stage: OpportunityStage;
  stage_label: string;
  amount: string | null;
  probability: number;
  expected_close: string | null;
  origin: string;
  owner: string | null;
  owner_name: string | null;
  description: string;
  won_date: string | null;
  lost_reason: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PipelineByStage {
  count: number;
  total: number;
}
export interface PipelineStats {
  by_stage: Record<string, PipelineByStage>;
  conversion_rate: number;
  won_total: number;
  margin_by_segment: Record<string, { count: number; total_margin: number; total_amount: number }>;
}

export type PoStatus =
  | "brouillon"
  | "confirmee"
  | "partielle"
  | "cloturee"
  | "annulee"
  | "previ";
export type ReceiptStatus = "en_attente" | "valide" | "annule";

export interface ConformityRow {
  label: string;
  ordered: number;
  received: number;
  invoiced: number;
  ok: boolean;
}

export interface PurchaseOrder {
  id: string;
  code: string;
  supplier: string | null;
  supplier_name: string | null;
  request: string | null;
  request_code: string | null;
  order_date: string;
  expected_date: string | null;
  status: PoStatus;
  status_label: string;
  is_global_rental: boolean;
  total: string | null;
  conformity: ConformityRow[];
  lines_count: number;
  created_by_name: string | null;
  created_at: string;
}

export type OfStatus =
  | "prevu"
  | "lance"
  | "en_cours"
  | "termine"
  | "cloture"
  | "annule";
export type OfScope = "atelier" | "chantier";

export interface OrdreFabrication {
  id: string;
  code: string;
  label: string;
  affaire: string | null;
  affaire_code: string | null;
  gamme: string | null;
  gamme_code: string | null;
  scope: OfScope;
  scope_label: string;
  article: string | null;
  article_code: string | null;
  quantity: string;
  status: OfStatus;
  status_label: string;
  planned_start: string | null;
  planned_end: string | null;
  calculated_hours: string;
  responsible: string | null;
  responsible_name: string | null;
  pointage_hours: string;
  pointages_count: number;
  created_at: string;
}

export interface SituationTravaux {
  id: string;
  code: string;
  affaire: string | null;
  affaire_code: string | null;
  label: string;
  period_start: string;
  period_end: string;
  amount: string | null;
  progress: number;
  status: string;
  status_label: string;
  ordres_count: number;
  ordered_hours: string;
  created_by_name: string | null;
  validated_by_name: string | null;
  validated_at: string | null;
}

export interface ChargeRow {
  code: string;
  label: string;
  scope: OfScope;
  status: OfStatus;
  calculated_hours: number;
  pointed_hours: number;
}
export interface ChargeStats {
  ordres: ChargeRow[];
  totals: {
    atelier: { calculated: number; pointed: number; count: number };
    chantier: { calculated: number; pointed: number; count: number };
  };
}

export type EquipementStatut =
  | "disponible"
  | "affecte"
  | "en_location"
  | "hors_service"
  | "maintenance";

export interface EquipementParc {
  id: string;
  code: string;
  label: string;
  registration: string;
  categorie: string;
  categorie_label: string;
  statut: EquipementStatut;
  statut_label: string;
  compteur_type: string;
  compteur_type_label: string;
  compteur_value: string;
  site: string;
  is_global_rental: boolean;
  proprietaire: string | null;
  proprietaire_code: string | null;
  proprietaire_gr: boolean | null;
  signe_618: boolean;
}

export interface DemandeMobilisation {
  id: string;
  code: string;
  label: string;
  affaire: string | null;
  affaire_code: string | null;
  ordre: string | null;
  departement: string;
  date_debut: string | null;
  date_fin: string | null;
  notes: string;
  statut: string;
  statut_label: string;
}

export interface LocationGR {
  id: string;
  code: string;
  partenaire: string | null;
  partenaire_name: string | null;
  equipement: string;
  equipement_code: string;
  equipement_label: string;
  affaire: string | null;
  affaire_code: string | null;
  reference_bc: string;
  reference_gr: string;
  reference_bl: string;
  date_debut: string | null;
  date_fin: string | null;
  periodicite: string;
  periodicite_label: string;
  tarif: string;
  devise: string | null;
  devise_code: string | null;
  montant_estime: string | null;
  lecture_initiale: string | null;
  lecture_finale: string | null;
  consommation: string | null;
  imputation_618: boolean;
  statut: string;
  statut_label: string;
  lectures_count: number;
}

export interface ParcStats {
  parc: {
    total: number;
    par_statut: Record<string, number>;
    global_rental: number;
    propre: number;
  };
  locations: {
    actives: number;
    total_montant_estime: number;
    rows: Array<{
      code: string;
      equipement: string | null;
      partenaire: string | null;
      affaire_code: string | null;
      montant_estime: number;
      devise: string | null;
      consommation: number;
      fin: string | null;
    }>;
  };
}

export interface Depot {
  id: string;
  code: string;
  label: string;
  site: string;
  responsable: string | null;
  responsable_label: string | null;
  description: string;
  is_active: boolean;
}

export type LotStatut = "disponible" | "partiel" | "epuise" | "bloque";

export interface LotMatiere {
  id: string;
  code: string;
  article: string;
  article_code: string | null;
  article_label: string | null;
  numero_lot: string;
  date_reception: string;
  date_peremption: string | null;
  quantite_initiale: string;
  quantite_restante: string;
  statut: LotStatut;
  certificats: string[];
}

export interface CertificatMatiere {
  id: string;
  code: string;
  lot: string;
  lot_code: string | null;
  article_code: string | null;
  type: "mtc" | "coc";
  numero_certificat: string;
  organisme: string;
  date_emission: string | null;
  date_validation: string | null;
  conforme: boolean;
}

export interface StockQuant {
  id: string;
  depot: string;
  depot_code: string;
  article: string;
  article_code: string;
  article_label: string;
  lot: string | null;
  lot_code: string | null;
  quantity: string;
  unit_cost: number;
  stock_value: string | null;
  has_amount_access: boolean;
}

export interface MouvementStock {
  id: string;
  code: string;
  type_mouvement: "reception" | "transfert" | "consommation" | "retour" | "inventaire";
  type_label: string;
  article: string;
  article_code: string | null;
  article_label: string | null;
  quantite: string;
  prix_unitaire: string | null;
  source: string | null;
  source_code: string | null;
  destination: string | null;
  destination_code: string | null;
  lot: string | null;
  lot_code: string | null;
  ordre: string | null;
  ordre_code: string | null;
  document_reference: string;
  date: string;
  executed: boolean;
  montant_total: string | null;
  has_amount_access: boolean;
  notes: string;
}

export interface Inventaire {
  id: string;
  code: string;
  depot: string;
  depot_label: string;
  date: string;
  statut: "brouillon" | "en_cours" | "cloture" | "annule";
  responsable: string | null;
  responsable_label: string | null;
  note: string;
  ecart_total: string;
  lignes: Array<{
    id: string;
    article_code: string | null;
    article_label: string | null;
    lot_code: string | null;
    quantite_systeme: string;
    quantite_reelle: string;
    ecart: string;
  }>;
  created_at: string;
}

export interface ValorisationRow {
  depot: string;
  article: string;
  label: string;
  quantity: number;
  value: number;
  unit_cost: number;
  method: "fifo" | "peps" | "cump" | "pp";
  lot: string | null;
}

export interface StocksKpis {
  depots: number;
  lots: number;
  quants: number;
  value: number;
  has_amount_access: boolean;
}