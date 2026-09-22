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