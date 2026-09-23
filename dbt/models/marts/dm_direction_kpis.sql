/*
Modele dbt deprecie — rempli par le modele cibles contenant les KPIs Direction.
*/

select
    now()::date as as_of_date,
    (select count(*) from {{ source("etls_replica", "documents_document") }}) as documents_total,
    (select count(*) from {{ source("etls_replica", "workflow_task") }}) as workflow_taches,
    (select count(*) from {{ source("etls_replica", "commercial_opportunity") }} where is_active) as commercial_opportunites,
    (select count(*) from {{ source("etls_replica", "commercial_affaire") }} where status <> 'cloturee') as commercial_affaires,
    (select count(*) from {{ source("etls_replica", "achats_purchaseorder") }} where status <> 'annulee') as achats_bc,
    (select count(*) from {{ source("etls_replica", "operations_ordrefabrication") }} where status not in ('annule','termine','cloture')) as operations_of_en_cours,
    (select count(*) from {{ source("etls_replica", "logistique_equipementparc") }}) as logistique_equipements,
    (select count(*) from {{ source("etls_replica", "logistique_equipementparc") }} where statut = 'disponible') as logistique_disponibles,
    (select count(*) from {{ source("etls_replica", "stocks_lotmatiere") }} where statut <> 'disponible') as stocks_lots_non_dispo,
    (select count(*) from {{ source("etls_replica", "stocks_stockquant") }}) as stocks_quants,
    (select count(*) from {{ source("etls_replica", "qualite_nonconformite") }} where statut <> 'cloturee') as qualite_nc_ouvertes,
    (select count(*) from {{ source("etls_replica", "hse_incident") }} where statut <> 'cloture') as hse_incidents_ouverts,
    (select count(*) from {{ source("etls_replica", "hse_permistravail") }} where statut = 'actif') as hse_permis_actifs,
    (select count(*) from {{ source("etls_replica", "maintenance_actif") }} where statut in ('en_panne','en_maintenance')) as maintenance_arrets,
    (select count(*) from {{ source("etls_replica", "maintenance_ordretravail") }} where statut not in ('cloture','annule')) as maintenance_ot_ouverts,
    (select count(*) from {{ source("etls_replica", "rh_paie_employe") }} where statut = 'actif') as rh_effectif,
    (select count(*) from {{ source("etls_replica", "juridique_courrier") }} where statut in ('recu','enregistre')) as juridique_courriers_a_classer,
    (select count(*) from {{ source("etls_replica", "juridique_contentieux") }} where statut in ('ouvert','en_instruction')) as juridique_contentieux_ouverts,
    (select count(*) from {{ source("etls_replica", "comptabilite_engagement") }} where statut <> 'annule') as compta_engagements,
    (select count(*) from {{ source("etls_replica", "controle_gestion_budget") }} where statut = 'approuve') as controle_budgets_approuves