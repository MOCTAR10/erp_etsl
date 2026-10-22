-- Commandes fournisseurs M2 (Couche D) : statut, affaire, GLOBAL RENTAL (fil rouge 618).
select
    id,
    code,
    supplier_id,
    affaire_id,
    order_date,
    expected_date,
    status,
    is_global_rental,
    analytic_id,
    (status in ('confirmee', 'partielle')) as is_ouverte,
    (status = 'annulee') as is_annulee
from {{ source("etls_replica", "achats_purchaseorder") }}
