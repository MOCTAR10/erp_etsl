select
    current_date as as_of_date,
    count(*) filter (where retention_end <= current_date) as retention_due,
    count(*) filter (where retention_end <= current_date + 30) as retention_due_j30,
    count(*) filter (where retention_end <= current_date + 60) as retention_due_j60,
    count(*) filter (where retention_end <= current_date + 90) as retention_due_j90
from {{ ref("dm_documents") }}