with opportunities as (
    select
        id,
        code,
        subject,
        stage,
        amount,
        is_active,
        won_date,
        client_id,
        created_at
    from {{ source("etls_replica", "commercial_opportunity") }}
),
affaires as (
    select
        id,
        code,
        title,
        affaire_type,
        contract_amount,
        margin,
        status,
        start_date,
        end_date,
        client_id,
        opportunity_id
    from {{ source("etls_replica", "commercial_affaire") }}
)
select
    o.id,
    o.code,
    o.subject,
    o.stage,
    o.amount,
    o.is_active,
    o.won_date,
    o.created_at,
    (o.amount is not null and o.stage = 'gagne') as is_won,
    a.id as affaire_id,
    a.contract_amount,
    a.margin,
    a.status as affaire_status
from opportunities o
left join affaires a on a.client_id = o.client_id and a.opportunity_id = o.id