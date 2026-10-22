/** Réponses des services de pilotage (couche décisionnelle) consommées par la page Direction. */

export interface SemaineCf {
  semaine: number;
  debut: string;
  fin: string;
  encaissements: string;
  decaissements: string;
  flux_net: string;
  solde_fin: string;
}

export interface SeuilBudget {
  budget: string;
  libelle: string;
  montant: string;
  realise: string;
  taux_pct: string;
  niveau: "alerte" | "atteint" | "depasse" | null;
}

export interface Pilotage {
  cashflow: { ouverture: string; semaines: SemaineCf[]; solde_final: string; semaines_tension: number[] };
  pipe_budget: {
    annee: number;
    budget_produits: string;
    realise: string;
    pipe_pondere: { signe: string; en_cours: string; prospect: string; total: string };
    atterrissage: string;
    reste_a_couvrir: string;
    couverture_pct: string | null;
  };
  seuils_budget: SeuilBudget[];
  retention: { cubes: number; scelles: Record<string, number>; retention_financier_ans: string; retention_operationnel_ans: string };
  blocage_avant_cloture: boolean;
  voit_non_cloture: boolean;
  periodes_cloturees: string[];
  parametres_provisoires: boolean;
}

export interface Scelle {
  id: string;
  mart: string;
  type_donnees: string;
  nb_lignes: number;
  sha256: string;
  conserve_jusqu_au: string;
  integre: boolean;
  created_at: string;
}

export interface AlerteCal {
  type: string;
  code: string;
  libelle: string;
  date_echeance: string;
  jours: number;
  bande: string;
}

export interface IndicateursCommerciaux {
  prix_moyen: string | null;
  offres_gagnees: number;
  taux_transformation_pct: string | null;
  score_moyen: string | null;
  clients_sous_seuil: number;
  clients_70_plus: number;
}

export interface ItpCnd {
  itp?: { plans: number; plans_approuves: number; points: number; points_arret_en_attente: number; points_leves: number; points_non_conformes: number; taux_levee: number };
  cnd?: { controles: number; en_cours: number; par_methode: Record<string, number>; conformes: number; sous_reserve: number; non_conformes: number; taux_rejet: number };
}

export interface CapaLigne {
  origine: "qualite" | "hse";
  total: number;
  ouvertes: number;
  echues: number;
  cloturees: number;
  delai_moyen_cloture_jours: string | null;
  efficacite_verifiee: number;
  efficaces: number;
  taux_efficacite_pct: string | null;
}

export interface EtatBi {
  fraicheur: { statut: "a_jour" | "en_retard" | "jamais"; rafraichi_le: string | null; age_minutes: number | null; seuil_minutes: number };
  fraicheur_provisoire: boolean;
  capa: CapaLigne[];
  marts: string[];
  staging: string[];
}
