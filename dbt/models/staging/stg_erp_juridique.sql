with conventions as (
    select
        id,
        code,
        type,
        titre,
        montant,
        date_debut,
        date_fin,
        statut
    from {{ source("etls_replica", "juridique_convention") }}
),
cautions as (
    select
        id,
        code,
        type,
        beneficiaire,
        montant,
        date_echeance,
        statut
    from {{ source("etls_replica", "juridique_caution") }}
),
assurances as (
    select
        id,
        code,
        type,
        numero_police,
        prime_annuelle,
        date_debut,
        date_echeance,
        statut
    from {{ source("etls_replica", "juridique_assurance") }}
)
select
    id,
    code,
    'convention' as nature,
    type,
    coalesce(titre, '') as libelle,
    montant as montant,
    date_fin as date_echeance,
    statut
from conventions
union all
select
    id,
    code,
    'caution' as nature,
    type,
    coalesce(beneficiaire, '') as libelle,
    montant as montant,
    date_echeance,
    statut
from cautions
union all
select
    id,
    code,
    'assurance' as nature,
    type,
    coalesce(numero_police, '') as libelle,
    prime_annuelle as montant,
    date_echeance,
    statut
from assurances