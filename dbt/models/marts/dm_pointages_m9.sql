-- Pointages M9 (Couche D) : heures par employe et par mois, sans ressaisie depuis les saisies de temps.
-- Meme regle que rh_paie.services.heures_supplementaires : heures productives = normal + supplementaire, heures sup.
-- calculees PAR SEMAINE ISO au-dela de la duree legale (tranche 1 jusqu'au seuil 2, tranche 2 au-dela).
-- Les parametres (DUREE_LEGALE_HEBDO, HS_SEUIL_2) viennent de la table de parametres de paie en vigueur le 1er du mois.
with semaines as (
    select
        s.employe_id,
        date_trunc('month', s.date)::date as periode,
        date_trunc('week', s.date)::date as semaine,
        sum(s.heures) filter (where s.type in ('normal', 'supplementaire')) as heures_semaine,
        sum(s.heures) filter (where s.type = 'nuit') as heures_nuit,
        sum(s.heures) filter (where s.type = 'astreinte') as heures_astreinte
    from {{ source("etls_replica", "rh_paie_saisietemps") }} s
    group by 1, 2, 3
),
parametres as (
    select
        w.employe_id,
        w.periode,
        w.semaine,
        w.heures_semaine,
        w.heures_nuit,
        w.heures_astreinte,
        (select p.valeur from {{ source("etls_replica", "rh_paie_parametrepaie") }} p
          where p.code = 'DUREE_LEGALE_HEBDO' and p.date_effet <= w.periode
            and (p.date_fin is null or p.date_fin >= w.periode)
          order by p.date_effet desc limit 1) as legale,
        (select p.valeur from {{ source("etls_replica", "rh_paie_parametrepaie") }} p
          where p.code = 'HS_SEUIL_2' and p.date_effet <= w.periode
            and (p.date_fin is null or p.date_fin >= w.periode)
          order by p.date_effet desc limit 1) as seuil2
    from semaines w
)
select
    employe_id,
    to_char(periode, 'YYYY-MM') as periode,
    coalesce(sum(heures_semaine), 0) as heures_productives,
    coalesce(sum(greatest(0, least(heures_semaine, seuil2) - legale)), 0) as heures_tranche_1,
    coalesce(sum(greatest(0, heures_semaine - seuil2)), 0) as heures_tranche_2,
    coalesce(sum(heures_nuit), 0) as heures_nuit,
    coalesce(sum(heures_astreinte), 0) as heures_astreinte,
    (bool_or(legale is null or seuil2 is null)) as parametres_absents,
    current_date as as_of_date
from parametres
group by employe_id, periode
