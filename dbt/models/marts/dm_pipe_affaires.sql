-- Pipe commercial pondere (Couche D) : opportunites actives par etape, ponderation 90 / 60 / 25 % (signe / en cours /
-- prospect, meme regle que commercial.services.pipe_pondere avec les ponderations par defaut), et affaires par statut.
select
    'opportunite' as objet,
    o.stage as etape,
    case
        when o.stage = 'gagne' then 'signe'
        when o.stage in ('offre', 'negociation') then 'en_cours'
        when o.stage in ('prospection', 'qualification') then 'prospect'
    end as categorie,
    count(*) as nombre,
    coalesce(sum(o.amount), 0) as montant_brut,
    round(coalesce(sum(o.amount), 0) * case
        when o.stage = 'gagne' then 0.90
        when o.stage in ('offre', 'negociation') then 0.60
        when o.stage in ('prospection', 'qualification') then 0.25
        else 0 end, 2) as montant_pondere,
    current_date as as_of_date
from {{ source("etls_replica", "commercial_opportunity") }} o
where o.is_active
group by o.stage
union all
select
    'affaire' as objet,
    af.status as etape,
    null as categorie,
    count(*) as nombre,
    coalesce(sum(af.contract_amount), 0) as montant_brut,
    null as montant_pondere,
    current_date as as_of_date
from {{ source("etls_replica", "commercial_affaire") }} af
group by af.status
