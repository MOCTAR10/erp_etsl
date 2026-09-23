/*
Echeancier transverse : legal (conventions/cautions/assurances), RH (contrats),
maintenance (garanties/qualifications) et equivalences GED. Consomme par Superset.
*/

with juridique as (
    select
        code,
        nature,
        type,
        libelle,
        date_echeance,
        statut,
        case
            when date_echeance <= current_date then 'EXPIRED'
            when date_echeance <= current_date + 30 then 'J30'
            when date_echeance <= current_date + 60 then 'J60'
            when date_echeance <= current_date + 90 then 'J90'
            else 'SAFE'
        end as alert_window
    from {{ ref("stg_erp_juridique") }}
    where date_echeance is not null
),
contracts as (
    select
        code as ref_code,
        'contrat' as nature,
        contrat_type as type,
        nom as libelle,
        date_fin as date_echeance,
        contrat_statut as statut,
        case
            when date_fin <= current_date then 'EXPIRED'
            when date_fin <= current_date + 30 then 'J30'
            when date_fin <= current_date + 60 then 'J60'
            when date_fin <= current_date + 90 then 'J90'
            else 'SAFE'
        end as alert_window
    from {{ ref("stg_erp_rh") }}
    where date_fin is not null
),
retention as (
    select
        id::text as ref_code,
        'ged' as nature,
        type_label as type,
        title as libelle,
        retention_end::date as date_echeance,
        'archive' as statut,
        alert_window
    from {{ ref("dm_retention_alerts") }}
    where alert_window <> 'SAFE'
),
conventions as (
    select code, nature, type, libelle, date_echeance, statut, alert_window
    from juridique
    where nature = 'convention' and statut in ('signe', 'en_signature')
),
cautions as (
    select code, nature, type, libelle, date_echeance, statut, alert_window
    from juridique
    where nature = 'caution'
),
assurances as (
    select code, nature, type, libelle, date_echeance, statut, alert_window
    from juridique
    where nature = 'assurance'
)
select
    ref_code,
    nature,
    type,
    libelle,
    date_echeance,
    statut,
    (date_echeance - current_date) as days_remaining,
    alert_window
from contracts
union all
select
    code,
    nature,
    type,
    libelle,
    date_echeance,
    statut,
    (date_echeance - current_date) as days_remaining,
    alert_window
from conventions
union all
select
    code,
    nature,
    type,
    libelle,
    date_echeance,
    statut,
    (date_echeance - current_date) as days_remaining,
    alert_window
from cautions
union all
select
    code,
    nature,
    type,
    libelle,
    date_echeance,
    statut,
    (date_echeance - current_date) as days_remaining,
    alert_window
from assurances
union all
select
    ref_code,
    nature,
    type,
    libelle,
    date_echeance,
    statut,
    (date_echeance - current_date) as days_remaining,
    alert_window
from retention