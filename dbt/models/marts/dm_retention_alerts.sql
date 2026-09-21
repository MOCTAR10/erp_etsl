select
    d.id,
    d.title,
    d.type_label,
    d.project_code,
    d.reference,
    d.retention_end,
    current_date as as_of_date,
    (d.retention_end - current_date) as days_remaining,
    case
        when d.retention_end <= current_date then 'EXPIRED'
        when d.retention_end <= current_date + 30 then 'J30'
        when d.retention_end <= current_date + 60 then 'J60'
        when d.retention_end <= current_date + 90 then 'J90'
        else 'SAFE'
    end as alert_window
from {{ ref("dm_documents") }} as d
where d.retention_end is not null