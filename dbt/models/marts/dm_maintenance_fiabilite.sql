-- Fiabilite du parc (M8, Couche D) : MTBF / MTTR / disponibilite par machine, meme regle que
-- maintenance.services.fiabilite_actifs. Periode d'observation et heures de service par jour viennent de la
-- table de parametres ETSL (modifiables sans developpeur) ; `valeurs_provisoires` tant qu'ils ne sont pas confirmes.
with params as (
    select
        coalesce(max(valeur) filter (where code = 'OBSERVATION_JOURS'), 365)::float8 as obs_jours,
        coalesce(max(valeur) filter (where code = 'HEURES_PAR_JOUR'), 24)::float8 as h_jour,
        (count(*) filter (where statut_valeur = 'confirme') < 2) as valeurs_provisoires
    from {{ source("etls_replica", "maintenance_parametremaintenance") }}
),
interventions as (
    select
        o.actif_id,
        (o.type_ot in ('correctif', 'urgence')) as is_panne,
        extract(epoch from (
            least(o.date_fin, now())
            - greatest(o.date_debut, now() - p.obs_jours * interval '1 day')
        )) / 3600.0 as heures_arret
    from {{ source("etls_replica", "maintenance_ordretravail") }} o
    cross join params p
    where o.statut in ('termine', 'cloture', 'archive')
      and o.date_debut is not null
      and o.date_fin is not null
      and o.date_fin >= now() - p.obs_jours * interval '1 day'
      and o.date_debut <= now()
),
cumul as (
    select
        actif_id,
        count(*) filter (where is_panne) as pannes,
        sum(greatest(heures_arret, 0)) as heures_arret
    from interventions
    group by actif_id
),
base as (
    select
        a.id as actif_id,
        a.code as actif_code,
        a.designation,
        a.is_global_rental,
        coalesce(c.pannes, 0) as pannes,
        round(coalesce(c.heures_arret, 0)::numeric, 2) as heures_arret,
        round((greatest(least(p.obs_jours, coalesce(current_date - a.date_mise_en_service, p.obs_jours)), 0)
               * p.h_jour)::numeric, 2) as heures_requises,
        p.obs_jours::int as observation_jours,
        p.valeurs_provisoires
    from {{ source("etls_replica", "maintenance_actif") }} a
    cross join params p
    left join cumul c on c.actif_id = a.id
)
select
    actif_id,
    actif_code,
    designation,
    is_global_rental,
    pannes,
    heures_arret,
    heures_requises,
    case when pannes > 0 then round(heures_arret / pannes, 2) end as mttr_h,
    case when pannes > 0 then round((heures_requises - heures_arret) / pannes, 2) end as mtbf_h,
    case when heures_requises > 0
         then round((heures_requises - heures_arret) / heures_requises * 100, 2) end as disponibilite_pct,
    observation_jours,
    valeurs_provisoires,
    current_date as as_of_date
from base
