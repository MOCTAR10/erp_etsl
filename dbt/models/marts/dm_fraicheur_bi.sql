-- Fraîcheur de la Couche D (CL-OM-12, ETL horaire) : horodatage du dernier `dbt build` réussi et dernière écriture
-- vue sur le réplica. Lu par analytics.services.fraicheur_couche_d (écran Direction / BI) : au-delà du seuil
-- provisoire BI_FRAICHEUR_MAX_MIN, l'écran signale des datamarts en retard.
select
    now() as rafraichi_le,
    (select max(created_at) from {{ source("etls_replica", "accounting_kernel_accountmove") }}) as derniere_ecriture,
    (select max(updated_at) from {{ source("etls_replica", "documents_document") }}) as dernier_document
