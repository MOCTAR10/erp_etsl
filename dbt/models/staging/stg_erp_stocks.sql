-- Mouvements de stock M5 exécutés (Couche D) : type, article, quantité, valorisation au coût unitaire.
select
    id,
    code,
    type_mouvement,
    article_id,
    source_id,
    destination_id,
    ordre_id,
    analytic_id,
    date,
    quantite,
    coalesce(cout_unitaire, prix_unitaire, 0) * quantite as valeur
from {{ source("etls_replica", "stocks_mouvementstock") }}
where executed
