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

export type NormeSoudeur = "iso9606" | "asme_ix";
export type ProcedeSoudage = "smaw" | "gtaw" | "gmaw" | "fcaw";
export type StatutQualification = "valide" | "expiree" | "suspendue";

export interface Soudeur {
  id: string;
  code: string;
  nom: string;
  prenoms: string;
  matricule: string;
  qualification: string;
  is_active: boolean;
  display_name: string;
}

export interface QualificationSoudeur {
  id: string;
  code: string;
  soudeur: string;
  soudeur_code: string;
  soudeur_name: string;
  norme: NormeSoudeur;
  norme_label: string;
  procede: ProcedeSoudage;
  procede_label: string;
  position: string;
  groupe_materiaux: string;
  epaisseur_min: string;
  epaisseur_max: string;
  gamme_diametre: string;
  date_qualification: string;
  date_validite: string;
  statut: StatutQualification;
  statut_label: string;
  est_valide: boolean;
  certificat: string;
}

export type TypeWps = "wps" | "wpqr";
export type StatutWps = "brouillon" | "valide" | "obsolete";

export interface WpsWpqr {
  id: string;
  code: string;
  type: TypeWps;
  type_label: string;
  reference: string;
  norme: NormeSoudeur;
  norme_label: string;
  procede: ProcedeSoudage;
  procede_label: string;
  materiau: string;
  position: string;
  epaisseur: string;
  gaz_protection: string;
  parametres: Record<string, string>;
  revue: string;
  statut: StatutWps;
  statut_label: string;
  date_validation: string | null;
}

export type TypeControleQualite =
  | "visuel"
  | "dimensionnel"
  | "cnd"
  | "pda"
  | "itp"
  | "peinture";
export type ResultatControle = "conforme" | "reserve" | "non_conforme";
export type StatutControle = "en_attente" | "en_cours" | "valide" | "annule";

export interface ControleQualite {
  id: string;
  code: string;
  type_controle: TypeControleQualite;
  type_label: string;
  organisme: "interne" | "agrege";
  organisme_label: string;
  organisme_libelle: string;
  affaire: string | null;
  affaire_code: string | null;
  ordre: string | null;
  ordre_code: string | null;
  wps: string | null;
  wps_code: string | null;
  lot: string | null;
  lot_code: string | null;
  point_controle: string;
  exigence: string;
  date_controle: string;
  resultat: ResultatControle;
  resultat_label: string;
  statut: StatutControle;
  statut_label: string;
  notes: string;
  created_by_name: string | null;
}

export type SourceNC = "controle" | "client" | "fournisseur" | "interne";
export type GraviteNC = "mineure" | "majeure" | "critique";
export type TraitementNC =
  | "reprise"
  | "reparation"
  | "rejet"
  | "acceptation"
  | "arbitrage";
export type StatutNC = "signalee" | "analysee" | "en_traitement" | "cloturee";

export interface NonConformite {
  id: string;
  code: string;
  controle: string | null;
  controle_code: string | null;
  source: SourceNC;
  source_label: string;
  gravite: GraviteNC;
  gravite_label: string;
  description: string;
  traitement: TraitementNC;
  traitement_label: string;
  statut: StatutNC;
  statut_label: string;
  date_decision: string | null;
  archive: boolean;
  actions_count: number;
}

export type TypeCapa = "corrective" | "preventive";
export type StatutCapa = "ouverte" | "en_cours" | "cloturee";

export interface ActionCorrective {
  id: string;
  code: string;
  non_conformite: string;
  non_conformite_code: string;
  type: TypeCapa;
  type_label: string;
  description: string;
  responsable_name: string | null;
  echeance: string | null;
  statut: StatutCapa;
  statut_label: string;
  efficace: boolean | null;
}

export type StatutPv = "en_cours" | "reserve" | "receptionne" | "rejete";

export interface PvControle {
  id: string;
  code: string;
  affaire: string | null;
  affaire_code: string | null;
  ordre: string | null;
  ordre_code: string | null;
  intitule: string;
  date_pv: string;
  statut: StatutPv;
  statut_label: string;
  resultat: ResultatControle;
  resultat_label: string;
  reserve_motif: string;
  levee_reserve: string | null;
  retention_years: number;
  date_archivage: string | null;
  validated_by_name: string | null;
  notes: string;
}

export type TypePermis =
  | "chaud"
  | "hauteur"
  | "levage"
  | "confine"
  | "atex"
  | "froid"
  | "electrique"
  | "fouille"
  | "chimique";
export type StatutPermis = "demande" | "valide" | "actif" | "cloture" | "refuse" | "annule";

export interface PermisTravail {
  id: string;
  code: string;
  type_permis: TypePermis;
  type_label: string;
  affaire: string | null;
  affaire_code: string | null;
  ordre: string | null;
  ordre_code: string | null;
  emplacement: string;
  description: string;
  mesures: string;
  demandeur: string | null;
  demandeur_name: string | null;
  validateur: string | null;
  validateur_name: string | null;
  date_debut: string;
  date_fin: string | null;
  statut: StatutPermis;
  statut_label: string;
  date_validation: string | null;
  date_cloture: string | null;
  notes: string;
}

export type CriticiteRisque = "faible" | "moyenne" | "elevee" | "critique";
export type StatutRisque = "ouverte" | "traitee" | "cloturee";

export interface EvaluationRisque {
  id: string;
  code: string;
  lieux: string;
  activite: string;
  description: string;
  probabilite: number;
  gravite: number;
  score: number;
  criticite: CriticiteRisque;
  mesure: string;
  responsable: string | null;
  responsable_name: string | null;
  affaire: string | null;
  affaire_code: string | null;
  statut: StatutRisque;
  statut_label: string;
}

export type TypeIncident =
  | "incident"
  | "accident"
  | "quasi_accident"
  | "blessure"
  | "depart_feu"
  | "pollution"
  | "deversement"
  | "dommage_materiel"
  | "situation_dangereuse";
export type GraviteIncident = "mineure" | "majeure" | "critique";
export type StatutIncident = "declare" | "en_enquete" | "plan_action" | "cloture";

export interface Incident {
  id: string;
  code: string;
  type_incident: TypeIncident;
  type_label: string;
  gravite: GraviteIncident;
  gravite_label: string;
  date_evenement: string;
  lieu: string;
  description: string;
  personnes_impliquees: string;
  cause_immediate: string;
  cause_profonde: string;
  consequences: string;
  rapport: string;
  statut: StatutIncident;
  statut_label: string;
  archive: boolean;
  enqueteur_name: string | null;
  date_ouverture_enquete: string | null;
  date_rapport: string | null;
  actions_count: number;
}

export type TypeActionHse = "corrective" | "preventive";
export type StatutActionHse = "ouverte" | "en_cours" | "cloturee";

export interface ActionHse {
  id: string;
  code: string;
  incident: string | null;
  incident_code: string | null;
  risque: string | null;
  risque_code: string | null;
  type: TypeActionHse;
  type_label: string;
  description: string;
  responsable: string | null;
  responsable_name: string | null;
  echeance: string | null;
  statut: StatutActionHse;
  statut_label: string;
  efficace: boolean | null;
  closed_at: string | null;
}

export type StatutAtex = "disponible" | "quarantaine" | "ecarte";

export interface EquipementAtex {
  id: string;
  code: string;
  designation: string;
  zone_atex: string;
  marquage: string;
  fabricant: string;
  numero_serie: string;
  certificat: string;
  date_expiration_certificat: string | null;
  certificat_expire: boolean;
  date_derniere_inspection: string | null;
  prochaine_inspection: string | null;
  statut: StatutAtex;
  statut_label: string;
  notes: string;
}

export type TypeFormation = "formation" | "demonstration" | "causerie" | "exercice" | "campagne" | "recyclage";
export type StatutFormation = "planifiee" | "realisee" | "annulee";

export interface FormationSecurite {
  id: string;
  code: string;
  type_session: TypeFormation;
  type_label: string;
  theme: string;
  formateur: string;
  organisme: string;
  date_session: string;
  duree_heures: string;
  nb_participants: number;
  evalue: boolean;
  statut: StatutFormation;
  statut_label: string;
  notes: string;
}

export type TypeEpi =
  | "casque"
  | "lunettes"
  | "ecran_facial"
  | "protection_auditive"
  | "gants"
  | "chaussures"
  | "veste_haute_visibilite"
  | "harnais"
  | "masque"
  | "baudrier";
export type StatutEpi = "en_usage" | "disponible" | "rendu" | "hors_service";

export interface Epi {
  id: string;
  code: string;
  type_epi: TypeEpi;
  type_label: string;
  designation: string;
  taille: string;
  beneficiaire: string | null;
  beneficiaire_name: string | null;
  date_dotation: string;
  date_renouvellement: string | null;
  a_renouveler: boolean;
  statut: StatutEpi;
  statut_label: string;
  notes: string;
}

export type TypeDechet =
  | "huiles"
  | "solvants"
  | "batteries"
  | "peintures"
  | "dib"
  | "deee"
  | "metaux"
  | "papier_carton";
export type StatutBSD = "en_attente" | "emis" | "traite";

export interface BordereauDechet {
  id: string;
  code: string;
  type_dechet: TypeDechet;
  type_label: string;
  quantite: string;
  unite: string;
  unite_label: string;
  transporteur: string | null;
  transporteur_name: string | null;
  numero_bsd: string;
  date_enlevement: string | null;
  destination: string;
  statut: StatutBSD;
  statut_label: string;
  notes: string;
}

export interface HseStats {
  jours_sans_accident: number | null;
  incidents_ouverts: number;
  incidents_critiques: number;
  actions_ouvertes: number;
  permis_actifs: number;
  risques_critiques: number;
  epi_a_renouveler: number;
  formations_prevues: number;
  bsd_en_attente: number;
  atex_quarantaine: number;
}