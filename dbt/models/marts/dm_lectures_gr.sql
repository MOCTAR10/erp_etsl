-- Releves de compteur des prestations GLOBAL RENTAL (M4 -> M8/M10, Couche D) : premiere lecture, derniere lecture
-- et consommation par prestation, sans ressaisie.
select
    lo.id as location_id,
    lo.code as location_code,
    count(lc.id) as nb_lectures,
    (array_agg(lc.valeur order by lc.date, lc.created_at))[1] as premiere_valeur,
    (array_agg(lc.valeur order by lc.date desc, lc.created_at desc))[1] as derniere_valeur,
    max(lc.valeur) - min(lc.valeur) as consommation,
    max(lc.date) as derniere_lecture_le,
    current_date as as_of_date
from {{ source("etls_replica", "logistique_locationgr") }} lo
join {{ source("etls_replica", "logistique_lecturecompteur") }} lc on lc.location_id = lo.id
group by lo.id, lo.code
