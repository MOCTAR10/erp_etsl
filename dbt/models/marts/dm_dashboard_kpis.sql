with aggregations as (
    select
        current_date as as_of_date,
        (select count(*) from {{ ref("dm_documents") }} where status = 'archived')
            as documents_archived,
        (select count(*) from {{ ref("dm_documents") }} where status <> 'archived')
            as documents_in_progress,
        (select coalesce(sum(size_bytes), 0) from {{ ref("dm_documents") }})
            as storage_bytes,
        (select count(*) from {{ ref("dm_workflow") }} where status = 'pending')
            as workflow_pending,
        (
            select count(*)
            from {{ ref("dm_workflow") }}
            where status = 'pending' and due_date < now()
        ) as workflow_overdue
)
select *
from aggregations