-- Compteurs du parc (M8, Couche D) : une ligne par plan preventif, meme regle que
-- maintenance.models.PlanPreventif.motif_echeance. Le compteur lu est celui de l'equipement GLOBAL RENTAL lie
-- (releve logistique) pour un actif GR, sinon celui de l'actif.
select
    p.id as plan_id,
    p.code as plan_code,
    a.code as actif_code,
    a.designation,
    a.compteur_type,
    case when a.is_global_rental and a.equipement_gr_id is not null then e.compteur_value
         else a.compteur_value end as compteur_lu,
    p.dernier_compteur,
    p.intervalle_compteur,
    p.dernier_compteur + p.intervalle_compteur as prochain_compteur,
    p.derniere_date + p.periodicite_jours as prochaine_date,
    case
        when p.intervalle_compteur is not null
             and (case when a.is_global_rental and a.equipement_gr_id is not null then e.compteur_value
                       else a.compteur_value end) >= p.dernier_compteur + p.intervalle_compteur then 'compteur'
        when p.periodicite_jours is not null
             and current_date >= p.derniere_date + p.periodicite_jours then 'calendaire'
    end as motif_echeance,
    current_date as as_of_date
from {{ source("etls_replica", "maintenance_planpreventif") }} p
join {{ source("etls_replica", "maintenance_actif") }} a on a.id = p.actif_id
left join {{ source("etls_replica", "logistique_equipementparc") }} e on e.id = a.equipement_gr_id
where p.en_vigueur
  and a.statut not in ('hors_service', 'reforme')
