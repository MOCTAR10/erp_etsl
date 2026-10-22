-- Ordres de fabrication M3 (Couche D) : périmètre atelier / chantier, statut, planning, heures calculées.
select
    id,
    code,
    affaire_id,
    scope,
    status,
    planned_start,
    planned_end,
    calculated_hours,
    (status in ('lance', 'en_cours')) as is_en_cours,
    (status in ('termine', 'cloture')) as is_termine,
    (planned_end is not null and planned_end < current_date and status in ('prevu', 'lance', 'en_cours')) as is_en_retard
from {{ source("etls_replica", "operations_ordrefabrication") }}
