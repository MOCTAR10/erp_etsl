select
    id,
    code,
    type_incident,
    gravite,
    date_evenement,
    lieu,
    statut,
    archive,
    (statut = 'cloture') as is_cloture,
    (type_incident in ('accident', 'blessure')) as is_accident
from {{ source("etls_replica", "hse_incident") }}