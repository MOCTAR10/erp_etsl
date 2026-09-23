with actifs as (
    select
        id,
        code,
        designation,
        categorie,
        statut,
        is_global_rental,
        signe_618,
        compteur_type,
        compteur_value
    from {{ source("etls_replica", "maintenance_actif") }}
),
ordres as (
    select
        id,
        code,
        type_ot,
        priorite,
        statut,
        date_demande,
        date_debut,
        date_fin,
        heures_mo,
        tarif_horaire,
        cout_pieces,
        actif_id
    from {{ source("etls_replica", "maintenance_ordretravail") }}
)
select
    a.id,
    a.code as actif_code,
    a.designation,
    a.categorie,
    a.statut as actif_statut,
    a.is_global_rental,
    a.signe_618,
    a.compteur_value,
    (a.statut = 'operationnel') as is_operationnel,
    (a.statut in ('en_panne', 'en_maintenance')) as is_en_arret,
    o.id as ot_id,
    o.code as ot_code,
    o.type_ot,
    o.priorite,
    o.statut as ot_statut,
    o.heures_mo,
    o.tarif_horaire,
    o.cout_pieces
from actifs a
left join ordres o on o.actif_id = a.id