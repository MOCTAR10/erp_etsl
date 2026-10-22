-- CAPA qualité (M6) et HSE (M7) — Couche D : ouvertes, échues, clôturées, délai moyen de clôture, efficacité.
-- Même règle que analytics.services.indicateurs_capa (test analytics/test_ecarts_a4.py) :
--   échue = échéance < aujourd'hui et non clôturée ; délai = jours entre création et clôture (actions clôturées datées) ;
--   taux d'efficacité = efficaces / efficacité vérifiée (efficace renseigné), en %.
with capa as (
    select 'qualite' as origine, statut, echeance, efficace, created_at, closed_at
    from {{ source("etls_replica", "qualite_actioncorrective") }}
    union all
    select 'hse' as origine, statut, echeance, efficace, created_at, closed_at
    from {{ source("etls_replica", "hse_actionhse") }}
),
origines as (
    select 'qualite' as origine
    union all
    select 'hse'
)
select
    o.origine,
    count(c.statut) as total,
    count(c.statut) filter (where c.statut <> 'cloturee') as ouvertes,
    count(c.statut) filter (where c.statut <> 'cloturee' and c.echeance < current_date) as echues,
    count(c.statut) filter (where c.statut = 'cloturee') as cloturees,
    round(avg((c.closed_at::date - c.created_at::date)) filter (where c.statut = 'cloturee' and c.closed_at is not null), 1)
        as delai_moyen_cloture_jours,
    count(c.statut) filter (where c.efficace is not null) as efficacite_verifiee,
    count(c.statut) filter (where c.efficace) as efficaces,
    case when count(c.statut) filter (where c.efficace is not null) = 0 then null
         else round(100.0 * count(c.statut) filter (where c.efficace)
                    / count(c.statut) filter (where c.efficace is not null), 1) end as taux_efficacite_pct,
    current_date as as_of_date
from origines o
left join capa c on c.origine = o.origine
group by o.origine
