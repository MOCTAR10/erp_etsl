-- CAPA (actions correctives / préventives) qualité M6 et HSE M7, en une seule vue (Couche D).
-- Échue = échéance dépassée et action non clôturée (même règle que qualite.ActionCorrective.en_retard).
select
    id,
    code,
    'qualite' as origine,
    type,
    statut,
    echeance,
    efficace,
    created_at,
    closed_at,
    (statut = 'cloturee') as is_cloturee,
    (echeance is not null and statut <> 'cloturee' and echeance < current_date) as is_echue
from {{ source("etls_replica", "qualite_actioncorrective") }}
union all
select
    id,
    code,
    'hse' as origine,
    type,
    statut,
    echeance,
    efficace,
    created_at,
    closed_at,
    (statut = 'cloturee') as is_cloturee,
    (echeance is not null and statut <> 'cloturee' and echeance < current_date) as is_echue
from {{ source("etls_replica", "hse_actionhse") }}
