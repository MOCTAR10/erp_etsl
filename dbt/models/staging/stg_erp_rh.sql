select
    e.id,
    e.code,
    e.civilite,
    e.nom,
    e.prenom,
    e.categorie,
    e.departement,
    e.site,
    e.statut as employe_statut,
    (e.statut = 'actif') as is_actif,
    c.id as contrat_id,
    c.code as contrat_code,
    c.type as contrat_type,
    c.date_debut,
    c.date_fin,
    c.salaire_base,
    c.statut as contrat_statut
from {{ source("etls_replica", "rh_paie_employe") }} as e
left join {{ source("etls_replica", "rh_paie_contrattravail") }} as c
    on c.employe_id = e.id