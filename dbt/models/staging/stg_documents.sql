select
    d.id,
    d.title,
    d.status,
    dt.label as type_label,
    dt.retention_years,
    d.project as project_code,
    d.counterparty,
    d.reference,
    d.amount,
    d.document_date,
    d.archived_at,
    d.created_at,
    coalesce(v.size, 0) as size_bytes,
    (
        coalesce(d.document_date, d.archived_at::date, d.created_at::date)
        + make_interval(years => dt.retention_years)
    ) as retention_end
from {{ source("etls_replica", "documents_document") }} as d
left join {{ source("etls_replica", "documents_documenttype") }} as dt
    on dt.id = d.type_id
left join {{ source("etls_replica", "documents_version") }} as v
    on v.id = d.current_version_id