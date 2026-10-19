export interface Me {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_active: boolean;
  /** Modules ERP lisibles (RF-59) — absent sur une session persistée d'avant. */
  modules?: string[];
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
  /** Pipe pondéré 90 / 60 / 25 % (signé / en cours / prospect) publié vers M11 (clôture M1). */
  pipe_pondere?: { signe: number; en_cours: number; prospect: number; total: number };
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

export interface EquipeAffectation {
  id: string;
  code: string;
  equipe: string;
  equipe_label: string;
  metier: string;
  ordre: string;
  ordre_code: string;
  date_debut: string;
  date_fin: string;
  effectif: number;
  statut: "planifiee" | "mobilisee" | "terminee";
  statut_label: string;
}

export interface PresenceChantier {
  id: string;
  ordre_code: string;
  employe_nom: string;
  date: string;
  statut: "present" | "absent" | "retard";
  statut_label: string;
  motif: string;
}

export interface ChargeRow {
  code: string;
  label: string;
  scope: OfScope;
  status: OfStatus;
  calculated_hours: number;
  pointed_hours: number;
}
export interface ChargeAlerte {
  scope: OfScope;
  week: string;
  planned_hours: number;
  capacity: number;
  overload_pct: number;
}
export interface ChargeStats {
  ordres: ChargeRow[];
  alertes?: ChargeAlerte[];
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

export interface TarifGR {
  id: string;
  code: string;
  partenaire: string;
  partenaire_code: string | null;
  equipement: string | null;
  equipement_code: string | null;
  categorie: string;
  categorie_label: string;
  periodicite: string;
  periodicite_label: string;
  tarif: string | null;
  penalite_jour: string | null;
  date_effet: string;
  version: number;
}

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
  emis_le: string | null;
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
  numero_coulee: string;
  motif_blocage: string;
  bloque_par_name: string | null;
  nc_blocage_code: string | null;
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
  valide_par_name: string | null;
  document: string | null;
  document_titre: string | null;
  conforme: boolean;
}

export interface AlertesStock {
  peremption_jours: number;
  provisoire: boolean;
  rows: { type: "stock_mini" | "peremption" | "fournisseur_non_agree"; article: string; libelle: string; lot: string | null; detail: string }[];
}

export interface ParametreStock {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  est_provisoire: boolean;
}

export interface ArticleStockConfig {
  id: string;
  article: string;
  article_code: string | null;
  article_label: string | null;
  seuil_minimal: string;
  lot_obligatoire: boolean;
  certificat_requis: boolean;
}

export interface TraceabiliteEntry {
  code: string;
  date: string;
  type_label: string;
  quantite: number;
  source: string | null;
  destination: string | null;
  ordre: string | null;
  reference: string;
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
  document: string | null;
  document_titre: string | null;
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

export interface ValorisationMensuelle {
  id: string;
  periode: string;
  depot: string;
  depot_code: string;
  quantite: string;
  valeur_stock: string | null;
  consommation: string | null;
  ventilation: Array<{ axe: string; libelle: string; valeur: string | null }>;
  has_amount_access: boolean;
}

export interface PlanInventaireTournant {
  id: string;
  code: string;
  depot: string;
  depot_label: string;
  periodicite_jours: number;
  articles_par_passage: number;
  prochaine_date: string;
  actif: boolean;
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
  approuve_le?: string | null;
  methode_cnd?: "" | "RT" | "UT" | "PT" | "MT";
  images_count?: number;
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
  /** ITP : points d'arrêt / d'observation (CL-OM-07). */
  points?: PointInspection[];
  points_arret_restants?: number;
}

export interface PointInspection {
  id: string;
  controle: string;
  ordre: number;
  description: string;
  type_point: "arret" | "observation";
  type_label: string;
  responsable_levee: string;
  statut: "en_attente" | "leve" | "non_conforme";
  statut_label: string;
  leve_par_name: string | null;
  leve_le: string | null;
  commentaire: string;
}

export interface BaremeCotisation {
  id: string;
  code: string;
  label: string;
  organisme: string;
  nature: "salariale" | "patronale";
  nature_label: string;
  base: "brut" | "salaire";
  taux: string;
  plafond: string | null;
  date_effet: string;
  date_fin: string | null;
  ordre: number;
  statut_valeur: "provisoire" | "confirme";
  source: string;
  reference_texte: string;
  confirme_le: string | null;
  est_provisoire: boolean;
}

export interface BaremeImpot {
  id: string;
  code: string;
  label: string;
  tranches: { plafond: number | null; taux: number }[];
  abattement_pct: string;
  cotisations_deductibles: boolean;
  date_effet: string;
  date_fin: string | null;
  statut_valeur: "provisoire" | "confirme";
  source: string;
  reference_texte: string;
}

export interface ParametrePaie {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  date_effet: string;
  date_fin: string | null;
  statut_valeur: "provisoire" | "confirme";
  source: string;
  reference_texte: string;
  est_provisoire: boolean;
}

export interface HistoriqueBareme {
  id: string;
  objet: string;
  code: string;
  action: string;
  par_email: string | null;
  le: string;
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
  prochain_niveau?: "superviseur" | "hse" | "dg" | null;
  date_debut: string;
  date_fin: string | null;
  statut: StatutPermis;
  statut_label: string;
  date_validation: string | null;
  date_cloture: string | null;
  notes: string;
  /** Test d'atmosphère (CL-OM-07) : requis avant démarrage pour chaud / confiné / ATEX / chimique. */
  gaz_obligatoire?: boolean;
  test_gaz_resultat?: "" | "conforme" | "non_conforme";
  test_gaz_valeur?: string;
  test_gaz_valide?: boolean;
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

export type CategorieActif =
  | "machine"
  | "engin"
  | "levage"
  | "atelier"
  | "chantier"
  | "outillage";
export type StatutActif =
  | "operationnel"
  | "en_maintenance"
  | "en_panne"
  | "hors_service"
  | "reforme";
export type TypeCompteurActif = "heures" | "km" | "aucun";

export interface Actif {
  id: string;
  code: string;
  designation: string;
  categorie: CategorieActif;
  categorie_label: string;
  fabricant: string;
  modele: string;
  numero_serie: string;
  site: string;
  statut: StatutActif;
  statut_label: string;
  en_arret: boolean;
  date_mise_en_service: string | null;
  garanti_jusqu: string | null;
  compteur_type: TypeCompteurActif;
  compteur_type_label: string;
  compteur_value: string;
  compteur_lecture: string | null;
  is_global_rental: boolean;
  equipement_gr: string | null;
  equipe_gr_code: string | null;
  signe_618: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export type TypeOT = "correctif" | "preventif" | "urgence" | "inspection";
export type PrioriteOT = "basse" | "moyenne" | "haute" | "critique";
export type StatutOT =
  | "demande"
  | "planifie"
  | "en_cours"
  | "termine"
  | "cloture"
  | "archive"
  | "annule";
export type DecisionOT = "reparation" | "mise_hors_service" | "reforme";

export interface OrdreTravail {
  id: string;
  code: string;
  actif: string;
  actif_code: string;
  actif_designation: string;
  type_ot: TypeOT;
  type_label: string;
  priorite: PrioriteOT;
  priorite_label: string;
  description: string;
  cause: string;
  demandeur: string | null;
  demandeur_name: string | null;
  technicien: string | null;
  technicien_name: string | null;
  date_demande: string;
  date_planifiee: string | null;
  date_debut: string | null;
  date_fin: string | null;
  heures_mo: string | null;
  tarif_horaire: string | null;
  cout_pieces: string | null;
  cout_main_oeuvre: string | null;
  cout_total: string | null;
  has_amount_access: boolean;
  decision: DecisionOT | "";
  decision_label: string | null;
  rapport: string;
  statut: StatutOT;
  statut_label: string;
  qualifie_le: string | null;
  qualifie_par_name: string | null;
  document: string | null;
  document_titre: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExigenceHabilitationMaintenance {
  id: string;
  categorie_actif: string;
  categorie_label: string;
  type_ot: string;
  type_label: string;
  mot_cle: string;
  actif: boolean;
}

export interface HistoriqueStatutOT {
  id: string;
  de: StatutOT | "";
  vers: StatutOT;
  par_name: string | null;
  le: string;
  commentaire: string;
}

export interface PlanPreventif {
  id: string;
  code: string;
  actif: string;
  actif_code: string;
  libelle: string;
  composant: string;
  periodicite_jours: number | null;
  intervalle_compteur: string | null;
  prochaine_date: string | null;
  prochain_compteur: string | null;
  compteur_actuel: string;
  echeance: string | null;
  prealerte: string | null;
  ot_ouvert: string | null;
  priorite: string;
}

export interface CalendrierPreventif {
  periode: string;
  provisoire: boolean;
  prealerte_jours: number;
  prealerte_pct: string;
  occurrences: { plan: string; actif: string; designation: string; libelle: string; composant: string; date: string; echu: boolean }[];
  compteurs: { plan: string; actif: string; libelle: string; compteur_actuel: string; prochain_compteur: string }[];
}

export type TypeInspection =
  | "visuelle"
  | "fonctionnelle"
  | "securite"
  | "levage"
  | "atex"
  | "metrologie";
export type ResultatInspection = "conforme" | "sous_reserve" | "non_conforme";
export type StatutInspection = "planifiee" | "realisee" | "annulee";

export interface Inspection {
  id: string;
  code: string;
  actif: string;
  actif_code: string;
  actif_designation: string;
  type_inspection: TypeInspection;
  type_label: string;
  date_inspection: string;
  prochaine_inspection: string | null;
  organisme: string;
  organisme_libelle: string;
  resultat: ResultatInspection | "";
  resultat_label: string | null;
  constat: string;
  intervenant: string | null;
  intervenant_name: string | null;
  statut: StatutInspection;
  statut_label: string;
  ot_genere: string | null;
  ot_genere_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface MaintenanceStats {
  ot_ouverts: number;
  ot_en_cours: number;
  ot_critiques: number;
  actifs_arret: number;
  actifs_operationnels: number;
  inspections_prevues: number;
  cout_total: number;
  heures_total: number;
}

// ── M9 — RH & Paie ─────────────────────────────────────────────────────────

export type CiviliteEmploye = "masculin" | "feminin";
export type StatutEmploye = "actif" | "conge" | "suspendu" | "sorti";
export type CategorieEmploye = "cadre" | "agent_maitrise" | "technicien" | "ouvrier";
export type TypeContrat = "cdd" | "cdi" | "chantier" | "mission" | "stage";
export type StatutContrat = "actif" | "essai" | "expire" | "resilie";
export type TypeQualificationRh = "habilitation" | "permis" | "certificat" | "diplome";
export type StatutRecrutement =
  | "demande"
  | "validee"
  | "candidats"
  | "entrevue"
  | "integre"
  | "annulee";
export type TypeFormationRh = "planifie" | "realisee" | "annulee";
export type TypeConge =
  | "annuel"
  | "rotation"
  | "maladie"
  | "maternite"
  | "sans_solde"
  | "exceptionnel";
export type StatutConge = "demande" | "approuve" | "valide" | "refuse" | "annule";
export type TypeSanction =
  | "rappel"
  | "avertissement"
  | "mise_a_pied"
  | "suspension"
  | "licenciement"
  | "autre";
export type StatutSanction = "constate" | "instruite" | "decidee" | "archivee";
export type TypeTemps = "normal" | "supplementaire" | "nuit" | "astreinte";
export type StatutTemps = "saisi" | "transfere";
export type NatureRubrique = "gain" | "retenue";
export type StatutBulletin = "brouillon" | "valide" | "cloture" | "annule";

export interface ContractActif {
  code: string;
  type: TypeContrat;
  type_label: string;
  date_debut: string;
  date_fin: string | null;
  a_renouveler: boolean;
}

export interface Employe {
  id: string;
  code: string;
  civilite: CiviliteEmploye;
  nom: string;
  prenom: string;
  nom_complet: string;
  date_naissance: string | null;
  lieu_naissance: string;
  nationalite: string;
  numero_securite_sociale: string;
  telephone: string;
  email: string;
  adresse: string;
  categorie: CategorieEmploye;
  fonction: string;
  departement: string;
  site: string;
  statut: StatutEmploye;
  matricule_cnps: string;
  date_embauche: string | null;
  date_sortie: string | null;
  contrat_actif: ContractActif | null;
  solde_conges: string;
  created_at: string;
  updated_at: string;
}

export interface ContratTravail {
  id: string;
  code: string;
  employe: string;
  employe_nom: string;
  type: TypeContrat;
  type_label: string;
  date_debut: string;
  date_fin: string | null;
  salaire_base: string | null;
  regime_horaire: string;
  lieu_affectation: string;
  statut: StatutContrat;
  statut_label: string;
  expire_dans: number | null;
  a_renouveler: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Qualification {
  id: string;
  code: string;
  employe: string;
  employe_nom: string;
  type: TypeQualificationRh;
  type_label: string;
  intitule: string;
  organisme: string;
  date_obtention: string | null;
  date_validite: string | null;
  expiree: boolean;
  a_renouveler: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Recrutement {
  id: string;
  code: string;
  poste: string;
  type: string;
  type_label: string;
  justification: string;
  responsable: string | null;
  responsable_name: string | null;
  date_souhaitee: string | null;
  statut: StatutRecrutement;
  statut_label: string;
  created_at: string;
  updated_at: string;
}

export interface Formation {
  id: string;
  code: string;
  theme: string;
  organisme: string;
  formateur: string;
  date_session: string;
  duree_heures: string;
  participants: string[];
  nb_participants: number;
  type: TypeFormationRh;
  type_label: string;
  evaluation: string;
  created_at: string;
  updated_at: string;
}

export interface DemandeConge {
  id: string;
  code: string;
  employe: string;
  employe_nom: string;
  type: TypeConge;
  type_label: string;
  date_debut: string;
  date_fin: string;
  nb_jours: number;
  motif: string;
  statut: StatutConge;
  statut_label: string;
  created_at: string;
  updated_at: string;
}

export interface Sanction {
  id: string;
  code: string;
  employe: string;
  employe_nom: string;
  type: TypeSanction;
  type_label: string;
  faits: string;
  rapport: string;
  date_constat: string;
  date_decision: string | null;
  statut: StatutSanction;
  statut_label: string;
  created_at: string;
  updated_at: string;
}

export interface SaisieTemps {
  id: string;
  code: string;
  employe: string;
  employe_nom: string;
  date: string;
  heures: string;
  type: TypeTemps;
  type_label: string;
  source: string;
  statut: StatutTemps;
  statut_label: string;
  created_at: string;
  updated_at: string;
}

export interface RubriquePaie {
  id: string;
  code: string;
  label: string;
  nature: NatureRubrique;
  nature_label: string;
  base: "fixe" | "salaire" | "brut";
  taux: string | null;
  ordre: number;
}

export interface BulletinLigne {
  id: string;
  bulletin: string;
  rubrique: string;
  rubrique_code: string;
  rubrique_label: string;
  nature: NatureRubrique;
  libelle: string;
  montant: string;
}

export interface BulletinPaie {
  document?: string | null;
  ordre_virement?: string | null;
  avertissement?: string;
  baremes_provisoires?: string[];
  charges_patronales?: string | null;
  disponible_le?: string | null;
  consulte_le?: string | null;
  move?: string | null;
  move_number?: string | null;
  id: string;
  code: string;
  employe: string;
  employe_nom: string;
  matricule: string;
  periode: string;
  salaire_base: string | null;
  brut: string | null;
  net: string | null;
  total_gains: string | null;
  total_retenues: string | null;
  lignes: BulletinLigne[];
  statut: StatutBulletin;
  statut_label: string;
  has_amount_access: boolean;
  created_at: string;
  updated_at: string;
}

export interface RhPaieStats {
  effectif: number;
  en_conge: number;
  contrats_expirants_30: number;
  conges_en_attente: number;
  qualifications_expirees: number;
  bulletins_mois: number;
}

export interface MasseSalariale {
  mois: string;
  bulletins: number;
  brut_total: string;
  net_total: string;
}

export type StatutReleve = "importe" | "valide";
export type StatutRapprochement = "brouillon" | "valide";
export type StatutEngagement = "brouillon" | "soumis" | "approuve" | "annule";
export type StatutPaiement = "brouillon" | "valide" | "annule";
export type StatutDeclarationTva = "brouillon" | "deposee";
export type StatutControleCompta = "planifie" | "realise" | "cloture";

export interface CompteBancaire {
  id: string;
  code: string;
  label: string;
  banque: string;
  numero: string;
  compte_comptable: string;
  compte_comptable_code: string;
  devise: string | null;
  devise_code: string | null;
  solde_initial: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LigneReleve {
  id: string;
  releve: string;
  date: string;
  libelle: string;
  reference: string;
  debit: string;
  credit: string;
  rapprochee: boolean;
}

export interface ReleveBancaire {
  id: string;
  code: string;
  compte_bancaire: string;
  compte_bancaire_label: string;
  date_debut: string;
  date_fin: string;
  solde_initial: string;
  solde_final: string;
  statut: StatutReleve;
  statut_label: string;
  source: string;
  source_label: string;
  total_debit: string;
  total_credit: string;
  lignes: LigneReleve[];
  anomalies: { type: string; message: string }[];
  created_at: string;
}

export interface RapprochementBancaire {
  id: string;
  code: string;
  compte_bancaire: string;
  compte_bancaire_label: string;
  date: string;
  statut: StatutRapprochement;
  statut_label: string;
  notes: string;
  lignes: {
    id: string;
    ligne_releve: string;
    ligne_libelle: string;
    ligne_date: string;
    debit: string;
    credit: string;
  }[];
  created_at: string;
}

export interface Engagement {
  id: string;
  code: string;
  objet: string;
  montant: string;
  compte_depense: string | null;
  compte_depense_code: string | null;
  fournisseur: string | null;
  fournisseur_name: string | null;
  statut: StatutEngagement;
  statut_label: string;
  date_engagement: string | null;
  demande_par: string | null;
  demande_par_name: string | null;
  total_paye: string;
  created_at: string;
  updated_at: string;
}

export interface Paiement {
  id: string;
  code: string;
  sens: "sortie" | "entree";
  sens_label: string;
  mode: string;
  mode_label: string;
  montant: string | null;
  date: string;
  compte_bancaire: string;
  compte_bancaire_label: string;
  engagement: string | null;
  engagement_code: string | null;
  tiers: string | null;
  tiers_name: string | null;
  facture: string | null;
  facture_code: string | null;
  imputation_618: boolean;
  reference: string;
  statut: StatutPaiement;
  statut_label: string;
  move: string | null;
  move_number: string | null;
  has_amount_access: boolean;
  created_at: string;
  updated_at: string;
}

export interface DeclarationTva {
  id: string;
  code: string;
  mois: string;
  taux_tva: string;
  taux_tva_code: string;
  base_imposable: string | null;
  tva_collectee: string | null;
  tva_deductible: string | null;
  net_a_payer: string | null;
  statut: StatutDeclarationTva;
  statut_label: string;
  has_amount_access: boolean;
  created_at: string;
}

export interface ControleInterne {
  id: string;
  code: string;
  libelle: string;
  reference_procedure: string;
  statut: StatutControleCompta;
  statut_label: string;
  responsable: string | null;
  responsable_name: string | null;
  date_prevue: string | null;
  date_realise: string | null;
  constat: string;
  created_at: string;
  updated_at: string;
}

export interface FiscalYear {
  id: string;
  year: number;
  start_date: string;
  end_date: string;
  status: string;
}

export type TypeBudget = "charge" | "produit";
export type StatutBudget = "brouillon" | "approuve" | "cloture";
export type StatutRevision = "brouillon" | "appliquee" | "annulee";
export type StatutClotureGestion = "en_attente" | "realisee";

export interface BudgetLigne {
  id: string;
  budget: string;
  period: string;
  period_number: number;
  period_label: string;
  montant: string;
}

export interface Budget {
  id: string;
  code: string;
  label: string;
  type_budget: TypeBudget;
  type_label: string;
  fiscal_year: string;
  axis: string | null;
  axis_code: string | null;
  analytic: string | null;
  analytic_code: string | null;
  analytic_label: string | null;
  montant: string | null;
  montant_lignes: string | null;
  statut: StatutBudget;
  statut_label: string;
  lignes: BudgetLigne[];
  nb_revisions: number;
  visa_daf_par: string | null;
  visa_daf_le: string | null;
  visa_cg_par: string | null;
  visa_cg_le: string | null;
  created_by: string | null;
  has_amount_access: boolean;
  created_at: string;
  updated_at: string;
}

export interface BudgetRevision {
  id: string;
  code: string;
  budget: string;
  budget_code: string;
  numero: number;
  date_revision: string;
  ancien_montant: string | null;
  nouveau_montant: string | null;
  commentaire: string;
  statut: StatutRevision;
  statut_label: string;
  visa_daf_par: string | null;
  visa_daf_le: string | null;
  visa_cg_par: string | null;
  visa_cg_le: string | null;
  created_by: string | null;
  created_by_name: string | null;
  has_amount_access: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClotureGestion {
  id: string;
  code: string;
  period: string;
  period_label: string;
  date_cloture: string | null;
  statut: StatutClotureGestion;
  statut_label: string;
  jours_ecoulement: number | null;
  conforme_j4: boolean;
  echeance_j4: string;
  echeance_j6: string;
  date_publication: string | null;
  reporting_statut: "a_temps" | "j6" | "hors_delai" | "en_attente";
  reporting_provisoire: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface MargeRow {
  analytic: string | null;
  code_axe: string;
  libelle: string;
  produits: string;
  charges: string;
  marge: string;
  taux_marge: string | null;
}

export interface MargesResult {
  rows: MargeRow[];
  totals: {
    produits: string;
    charges: string;
    marge: string;
    marge_hors_gr: string;
    cout_gr: string;
  };
}

export interface VarianceLigne {
  period: string;
  period_number: number;
  period_label: string;
  montant: string;
  realise: string;
  ecart: string;
  taux: string | null;
}

export interface VarianceResult {
  lignes: VarianceLigne[];
  totals: {
    montant: string;
    realise: string;
    ecart: string;
    taux: string | null;
    sous_activite: boolean;
  };
}

export interface CloturesStats {
  periodes: number;
  realisees: number;
  conformes_j4: number;
  en_attente: number;
  max_jours_ecoulement: number | null;
}

export type StatutCourrier = "recu" | "enregistre" | "classe" | "archive";
export type StatutConvention = "brouillon" | "en_signature" | "signe" | "cloture" | "resilie";
export type StatutContentieux = "ouvert" | "en_instruction" | "gagne" | "perdu" | "transaction" | "cloture";
export type StatutCaution = "en_cours" | "levee" | "appelee" | "expiree";
export type StatutAssurance = "active" | "a_renouveler" | "expiree" | "resiliee";
export type StatutReunion = "planifiee" | "tenue" | "cloturee";
export type StatutDossierGR = "brouillon" | "ouvert" | "cloture";
export type BandeEcheance = "expiree" | "j0" | "j15" | "j30" | "j60" | "j90";

export interface Courrier {
  id: string;
  code: string;
  sens: string;
  sens_label: string;
  type: string;
  type_label: string;
  objet: string;
  reference: string | null;
  tiers: string | null;
  tiers_name: string | null;
  date_courrier: string | null;
  date_reception: string | null;
  statut: StatutCourrier;
  statut_label: string;
  notes: string | null;
}

export interface Convention {
  id: string;
  code: string;
  type: string;
  type_label: string;
  titre: string;
  partenaire: string | null;
  partenaire_name: string | null;
  montant: string | null;
  date_debut: string | null;
  date_fin: string | null;
  renouvelable: boolean;
  statut: StatutConvention;
  statut_label: string;
  days_left: number | null;
  expiry_status: BandeEcheance | "en_cours";
  a_renouveler: boolean;
  has_amount_access: boolean;
  affaire_code: string | null;
}

export interface Contentieux {
  id: string;
  code: string;
  nature: string;
  nature_label: string;
  objet: string;
  partie_adverse: string | null;
  conseil_ext: string | null;
  montant_en_jeu: string | null;
  reference: string | null;
  date_ouverture: string;
  phase: string;
  phase_label: string;
  statut: StatutContentieux;
  statut_label: string;
  decision: string | null;
  has_amount_access: boolean;
}

export interface Caution {
  id: string;
  code: string;
  type: string;
  type_label: string;
  emetteur_name: string | null;
  beneficiaire: string;
  objet: string;
  montant: string | null;
  numero_instrument: string | null;
  date_emission: string;
  date_echeance: string;
  statut: StatutCaution;
  statut_label: string;
  days_left: number | null;
  expiry_status: BandeEcheance | "en_cours";
  has_amount_access: boolean;
  convention_code: string | null;
}

export interface Assurance {
  id: string;
  code: string;
  type: string;
  type_label: string;
  assureur_name: string | null;
  numero_police: string;
  prime_annuelle: string | null;
  date_debut: string;
  date_echeance: string;
  objets_couverts: string;
  statut: StatutAssurance;
  statut_label: string;
  nb_sinistres: number;
  sinistres: Array<{ date: string; detail: string }>;
  days_left: number | null;
  expiry_status: BandeEcheance | "en_cours";
  has_amount_access: boolean;
}

export interface Reunion {
  id: string;
  code: string;
  type: string;
  type_label: string;
  objet: string;
  date_reunion: string;
  lieu: string | null;
  animateur_name: string | null;
  participants_names: string[];
  statut: StatutReunion;
  statut_label: string;
  nb_decisions: number;
  nb_decisions_ouvertes: number;
  decisions: Array<{ decision: string; responsable: string; date_echeance: string; cloturee: boolean }>;
}

export interface DossierGlobalRental {
  id: string;
  code: string;
  partenaire_gr: string;
  partenaire_gr_name: string;
  affaire_code: string | null;
  reference_contrat: string | null;
  objet: string;
  montant_estime: string | null;
  signe_618: boolean;
  date_debut: string;
  date_fin: string;
  statut: StatutDossierGR;
  statut_label: string;
  references_documents: string[];
  has_amount_access: boolean;
}

export interface AlerteEcheance {
  type: "convention" | "caution" | "assurance";
  code: string;
  libelle: string;
  date_echeance: string;
  bande: BandeEcheance;
  jours: number;
  statut: string;
}

export interface AlertesResult {
  conventions: AlerteEcheance[];
  cautions: AlerteEcheance[];
  assurances: AlerteEcheance[];
  compteurs: Record<BandeEcheance, number>;
  total: number;
}

export interface JuridiqueStats {
  courriers: number;
  courriers_a_classer: number;
  conventions: number;
  conventions_a_renouveler: number;
  contentieux_ouverts: number;
  cautions_en_cours: number;
  assurances: number;
  assurances_a_renouveler: number;
  reunions_planifiees: number;
  dossiers_gr_ouverts: number;
}

/** Couche D — tableau de bord Direction (C1). */
export interface DashboardDirection {
  documents: { total: number; dossiers: number; par_statut: { status: string; count: number }[] };
  workflow: { circuits: number; taches_pending: number; taches_done: number; taches_en_retard: number };
  referentiels: { partners: number; articles: number; annexes: number };
  registres: { registres: number; entrees: number };
  commercial: {
    opportunites_ouvertes: number;
    pipeline_stages: number;
    taux_conversion: number | null;
    ca_gagne: number | null;
    affaires_actives: number;
  };
  achats: {
    da: number;
    consultations: number;
    bc: number;
    bc_en_cours: number;
    bl: number;
    rc: number;
    montant_bc: number | null;
  };
  operations: { of_en_cours: number };
  logistique: {
    equipements: number;
    disponibles: number;
    affectes: number;
    locations: number;
    locations_actives: number;
  };
  stocks: {
    depots: number;
    articles: number;
    lots: number;
    mouvements: number;
    lots_non_dispo: number;
    valorisation: number | null;
  };
  qualite: { nc_ouvertes: number; soudeurs: number; wps_valides: number; pv_sous_reserve: number };
  hse: {
    jours_sans_accident: number | null;
    incidents_ouverts: number;
    permis_actifs: number;
    actions_ouvertes: number;
    risques_critiques: number;
  };
  maintenance: {
    actifs: number;
    en_panne: number;
    en_maintenance: number;
    ot_ouverts: number;
    inspections_prevues: number;
    en_arret: number;
  };
  rh_paie: { effectif: number; en_conge: number; conges_en_attente: number; bulletins_mois: number };
  comptabilite: {
    engagements_a_visa: number;
    engagements_approuves: number;
    paiements_mois: number;
    declarations_tva: number;
  };
  controle_gestion: {
    budgets: number;
    budgets_approuves: number;
    revisions: number;
    clotures_realisees: number;
    conformite_j4: { conformes: number; periodes: number; taux: number };
  };
  juridique: {
    courriers: number;
    courriers_a_classer: number;
    conventions: number;
    contentieux_ouverts: number;
    cautions_en_cours: number;
    assurances: number;
  };
}

/** Couche D — reporting client pétrolier ASMR / HSE / Qualité (C2). */
export interface ReportingPetrolier {
  asmr: {
    equipements: number;
    operationnels: number;
    en_panne: number;
    en_maintenance: number;
    hors_service: number;
    en_arret: number;
    taux_disponibilite: number;
  };
  hse: {
    jours_sans_accident: number | null;
    incidents: number;
    incidents_ouverts: number;
    accidents: number;
    permis_actifs: number;
    permis_atex: number;
    equipements_atex_quarantaine: number;
    epi_a_renouveler: number;
  };
  qualite: {
    soudeurs_qualifies: number;
    soudeurs_expires: number;
    wps_valides: number;
    nc_total: number;
    nc_ouvertes: number;
    nc_critiques: number;
    pv_sous_reserve: number;
  };
}

/** Couche D — alerte d'échéance transverse (C3). */
export interface AlerteEcheanceItem {
  type: string;
  code: string | null;
  libelle: string;
  date_echeance: string | null;
  bande: string;
  jours: number | null;
  statut: string;
}

export interface AlertesAgregees {
  documents: AlerteEcheanceItem[];
  juridique: AlertesResult;
  rh: AlerteEcheanceItem[];
  maintenance: AlerteEcheanceItem[];
  compteurs: Record<BandeEcheance, number>;
  total: number;
}

/** Espace libre-service salarié (CL-OM-01 / CL-OM-06). */
export interface MonProfil {
  id: string;
  code: string;
  nom_complet: string;
  categorie: string;
  statut: string;
  solde_conges: number;
  acquis_annuel: number;
}

export interface MonBulletin {
  id: string;
  code: string;
  periode: string;
  salaire_base: string;
  brut: string;
  net: string;
  statut: string;
  statut_label: string;
  disponible_le: string | null;
  consulte_le: string | null;
  lignes: { id: number; libelle: string; nature: string; montant: string }[];
}

export interface MonConge {
  id: string;
  code: string;
  type: string;
  type_label: string;
  date_debut: string;
  date_fin: string;
  nb_jours: number;
  motif: string;
  statut: string;
  statut_label: string;
  created_at: string;
}

/** Tendances mensuelles non financières du cockpit Direction (null = pas de droit de lecture). */
export interface Tendances {
  mois: string[];
  series: {
    documents: number[] | null;
    incidents: number[] | null;
    ordres_travail: number[] | null;
  };
}

/** Signature électronique avancée (CL-OM-06). */
export interface SignatureRequestItem {
  id: string;
  title: string;
  document_title: string;
  version_number: number;
  status: "pending" | "completed" | "refused";
  expired: boolean;
  expires_at: string;
  completed_at: string | null;
  a_mon_tour: boolean;
  signataires: {
    id: string;
    name: string;
    email: string;
    order: number;
    status: "pending" | "signed" | "refused";
    signed_at: string | null;
    refusal_reason: string;
  }[];
}

export interface SignatureCertificate {
  request: string;
  title: string;
  status: string;
  document: string;
  version: number;
  document_sha256: string;
  document_intact: boolean;
  valid: boolean;
  method: string;
  signatures: { order: number; signer: string; email: string; signed_at: string; ip: string | null; seal: string; seal_valid: boolean }[];
}

/** TRIR / LTIR / LTIFR (lot 15, CDC M7 §9.7) — taux en chaîne décimale, null sans heures travaillées. */
export interface IndicateursHse {
  debut: string;
  fin: string;
  heures: string;
  enregistrables: number;
  avec_arret: number;
  jours_perdus: number;
  trir: string | null;
  ltir: string | null;
  ltifr: string | null;
}

/** Analyse d'écart budget / réalisé > 10 % à rendre sous 5 jours (lot 15, CDC M11 §4.4). */
export interface AnalyseEcart {
  id: string;
  code: string;
  budget_code: string;
  budget_label: string;
  period_label: string;
  ecart_pct: string;
  echeance: string;
  en_retard: boolean;
  statut: "a_analyser" | "analysee";
  statut_label: string;
  analyse: string;
}

/** Délégation temporaire des validations (lot 15b, EX-G-02). */
export interface Delegation {
  id: string;
  code: string;
  delegant_email: string;
  delegataire_email: string;
  date_debut: string;
  date_fin: string;
  motif: string;
  active: boolean;
  annulee_le: string | null;
}

/** Entrée du journal des accès (lot 15b, EX-G-10). */
export interface JournalAcces {
  id: number;
  cree_le: string;
  evenement: string;
  evenement_label: string;
  email: string;
  ip: string | null;
  chemin: string;
}


export interface AuditHse {
  id: string;
  code: string;
  type_audit: "audit" | "inspection";
  zone: string;
  date_prevue: string;
  score: number | null;
  statut: "planifie" | "realise" | "cloture";
  nb_constats: number;
  nb_ecarts_ouverts: number;
}

export interface Duer {
  id: string;
  code: string;
  annee: number;
  perimetre: string;
  version: number;
  statut: "brouillon" | "approuve";
  nb_risques: number;
  a_revoir: boolean;
}

export interface PlanUrgence {
  id: string;
  code: string;
  type_plan: string;
  type_label: string;
  intitule: string;
  periodicite_mois: number;
  dernier_exercice: string | null;
  prochain_exercice: string | null;
  en_retard: boolean;
}


export interface ParametreCompta {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  statut_valeur: "provisoire" | "confirme";
  est_provisoire: boolean;
}

export interface Lettrage {
  id: string;
  code: string;
  compte: string;
  compte_code: string;
  automatique: boolean;
  statut: "actif" | "annule";
  ecart: string | null;
  lignes: { id: string; piece: string | null; date: string; reference: string; debit: string | null; credit: string | null }[];
  has_amount_access: boolean;
}

export interface LettrageAnomalies {
  delai_jours: number;
  parametres_provisoires: boolean;
  anomalies: { ligne: string; motif: "sans_tiers" | "ancienne"; date: string; reference: string; debit: string | null; credit: string | null }[];
}

export interface RapprochementAuto {
  rapprochees: number;
  rapprochement: string | null;
  parametres_provisoires: boolean;
  ambigues: { id: string; date: string; libelle: string; debit: string | null; credit: string | null }[];
  lignes_sans_paiement: { id: string; date: string; libelle: string; debit: string | null; credit: string | null }[];
  paiements_sans_ligne: { id: string; code: string; date: string; sens: string; montant: string | null }[];
}

export interface ModeleFacture {
  id: string;
  code: string;
  entete: string;
  mentions_legales: string;
  conditions_paiement: string;
  coordonnees_bancaires: string;
  pied_page: string;
  delai_paiement_jours: number;
  statut_valeur: "provisoire" | "confirme";
  est_provisoire: boolean;
}

export interface FactureClient {
  id: string;
  code: string;
  nature: "facture" | "avoir";
  statut: "brouillon" | "emise";
  client: string;
  client_name: string;
  date: string;
  montant_ht: string | null;
  montant_tva: string | null;
  montant_ttc: string | null;
  move_number: string | null;
  avertissement_provisoire: boolean;
}

export interface AFacturer {
  jalons: { id: string; affaire: string; label: string; montant: string | null }[];
  situations: { id: string; code: string; affaire: string; label: string; montant: string | null }[];
}

export interface PeriodeRef {
  id: number;
  start_date: string;
  end_date: string;
  status: "open" | "closed";
}

export interface ControlesCloture {
  periode: string;
  bloquants: number;
  controles: { code: string; label: string; nb: number; bloquant: boolean; detail: string }[];
}

export interface ClotureMensuelle {
  id: string;
  period: number;
  periode: string;
  periode_statut: "open" | "closed";
  statut: "en_cours" | "cloturee";
  duree_minutes: string | null;
  dans_objectif: boolean | null;
  objectif_minutes: number | null;
  echeance_envoi: string | null;
  synthese: Record<string, string>;
  envoyee_le: string | null;
  destinataires: string[];
  retard: "cloture_en_retard" | "envoi_en_retard" | null;
  has_amount_access: boolean;
}

export interface ParametreGestion {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  statut_valeur: "provisoire" | "confirme";
  est_provisoire: boolean;
}

export interface SousActiviteRow {
  budget: string;
  code: string;
  label: string;
  analytic_label: string;
  budget_ecoule: string | null;
  realise: string | null;
  taux_sous_activite: string;
  centre: "90" | "91" | "99";
}

export interface SousActiviteResult {
  rows: SousActiviteRow[];
  provisoire: boolean;
}

export interface DoctrineLigne {
  classe: "A" | "B" | "C";
  montant: string | null;
  part: string;
  cible: string;
  conforme: boolean | null;
}

export interface DoctrineResult {
  lignes: DoctrineLigne[];
  non_classes: number;
  cible_coherente: boolean;
  provisoire: boolean;
}

export interface NiveauxMarge {
  produits: string | null;
  charges_directes: string | null;
  charges_structure: string | null;
  cout_gr: string | null;
  marge_brute: string | null;
  marge_operationnelle: string | null;
  marge_nette: string | null;
  taux_brute: string | null;
  taux_operationnelle: string | null;
  taux_nette: string | null;
}

export interface AtterrissageRow {
  budget: string;
  code: string;
  label: string;
  type_budget: "charge" | "produit";
  budget_annuel: string;
  realise: string;
  reste_a_venir: string;
  atterrissage: string;
  ecart_objectif: string;
}

export interface AtterrissageResult {
  rows: AtterrissageRow[];
  marge_a_terminaison: string | null;
  totaux: { produit: string; charge: string } | null;
}

export interface ParametreLogistique {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  statut_valeur: "provisoire" | "confirme";
  est_provisoire: boolean;
}

export interface GrAffaireRow {
  affaire: string | null;
  titre: string;
  analytic: number | null;
  non_affecte: boolean;
  compte: string;
  consommation: string;
  cout_gr: string | null;
  penalites: string | null;
  total_gr: string | null;
  marge_hors_gr: string | null;
  marge_apres_gr: string | null;
  locations: string[];
}

export interface GrAffairesResult {
  periode: string;
  compte: string;
  rows: GrAffaireRow[];
  total_gr: string | null;
  provisoire: boolean;
}

export interface ParametreMaintenance {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  statut_valeur: "provisoire" | "confirme";
  est_provisoire: boolean;
}

export interface FiabiliteRow {
  actif: string;
  designation: string;
  gr: boolean;
  pannes: number;
  heures_arret: string;
  heures_requises: string;
  mttr_h: string | null;
  mtbf_h: string | null;
  disponibilite_pct: string | null;
  alertes: string[];
}

export interface FiabiliteResult {
  observation_jours: number;
  heures_par_jour: string;
  seuil_disponibilite_pct: string;
  seuil_mtbf_h: string;
  provisoire: boolean;
  rows: FiabiliteRow[];
}

export interface PieceOT {
  id: string;
  article_code: string;
  article_label: string;
  depot_code: string;
  quantite: string;
  cout_unitaire: string | null;
  cout_total: string | null;
  mouvement_code: string;
}

export interface ReapproBesoin {
  article_id: string;
  article: string;
  designation: string;
  stock: string;
  seuil: string;
  a_commander: string;
}

export interface MaintenanceCoutRow {
  actif: string;
  designation: string;
  gr: boolean;
  compte: string;
  nb_ot: number;
  main_oeuvre: string | null;
  pieces: string | null;
  total: string | null;
}

export interface MaintenanceCoutsResult {
  periode: string;
  rows: MaintenanceCoutRow[];
  totaux: { gr_618: string | null; hors_gr: string | null };
}

export interface DocumentTypeOfficiel {
  id: string;
  code: string;
  label: string;
  officiel: boolean;
  officiel_provisoire: boolean;
}

export interface RechercheJuridiqueResult {
  q: string;
  documents: {
    id: string;
    title: string;
    status: string;
    reference: string;
    counterparty: string;
    liens: { objet_type: string; objet_id: string; objet_label: string; module: string }[];
  }[];
}

export type CubeAxe = "affaire" | "chantier" | "site" | "activite" | "centre" | "periode";

export interface CubeLecture {
  axes: CubeAxe[];
  rows: ({ produits: string; charges: string; cout_gr: string; marge: string } & Partial<Record<CubeAxe, string>>)[];
  totaux: { produits: string; charges: string; cout_gr: string; marge: string };
  periodes_archivees: string[];
  parametres_provisoires: boolean;
}

export interface CubeArchive {
  id: string;
  periode: string;
  nb_faits: number;
  sha256: string;
  conserve_jusqu_au: string;
  retention_provisoire: boolean;
  integre: boolean;
}

export interface ParametreCube {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  statut_valeur: "provisoire" | "confirme";
  est_provisoire: boolean;
}

export interface ConsommationsStock {
  depots: { periode: string; depot: string; valeur_stock: string | null; consommation: string | null }[];
  consommations_par_axe: { axe: string; valeur: string | null }[];
}
