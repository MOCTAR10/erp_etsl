-- Indicateurs qualite ITP / CND du reporting client petrolier (Couche D) : meme regle que
-- analytics.services._indicateurs_itp_cnd (controles annules exclus ; CND juges = controles valides).
select
    (select count(*) from {{ source("etls_replica", "qualite_controlequalite") }}
        where type_controle = 'itp' and statut <> 'annule') as itp_plans,
    (select count(*) from {{ source("etls_replica", "qualite_pointinspection") }} p
        join {{ source("etls_replica", "qualite_controlequalite") }} c on c.id = p.controle_id
        where c.type_controle = 'itp' and c.statut <> 'annule') as itp_points,
    (select count(*) from {{ source("etls_replica", "qualite_pointinspection") }} p
        join {{ source("etls_replica", "qualite_controlequalite") }} c on c.id = p.controle_id
        where c.type_controle = 'itp' and c.statut <> 'annule' and p.statut = 'leve') as itp_points_leves,
    (select count(*) from {{ source("etls_replica", "qualite_pointinspection") }} p
        join {{ source("etls_replica", "qualite_controlequalite") }} c on c.id = p.controle_id
        where c.type_controle = 'itp' and c.statut <> 'annule' and p.type_point = 'arret'
          and p.statut = 'en_attente') as itp_points_arret_en_attente,
    (select count(*) from {{ source("etls_replica", "qualite_controlequalite") }}
        where type_controle = 'cnd' and statut <> 'annule') as cnd_controles,
    (select count(*) from {{ source("etls_replica", "qualite_controlequalite") }}
        where type_controle = 'cnd' and statut = 'valide' and resultat = 'non_conforme') as cnd_non_conformes,
    (select count(*) from {{ source("etls_replica", "qualite_controlequalite") }}
        where type_controle = 'cnd' and statut = 'valide') as cnd_juges,
    current_date as as_of_date
