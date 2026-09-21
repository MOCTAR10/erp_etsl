select
    t.id,
    t.document_id,
    c.code as circuit_code,
    c.label as circuit_label,
    s.order as step_order,
    s.name as step_name,
    s.actor_role,
    t.status,
    t.assigned_to_id,
    u.email as assigned_to_email,
    t.created_at,
    t.due_date,
    t.completed_at,
    extract(
        epoch
        from (coalesce(t.completed_at, now()) - t.created_at)
    ) / 86400 as processing_days
from {{ source("etls_replica", "workflow_task") }} as t
left join {{ source("etls_replica", "workflow_circuit") }} as c on c.id = t.circuit_id
left join {{ source("etls_replica", "workflow_circuitstep") }} as s on s.id = t.step_id
left join {{ source("etls_replica", "users_user") }} as u on u.id = t.assigned_to_id