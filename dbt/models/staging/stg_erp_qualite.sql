select
    id,
    code,
    gravite,
    source,
    statut,
    archive,
    date_decision,
    (statut = 'cloturee') as is_cloture,
    (gravite = 'critique') as is_critique
from {{ source("etls_replica", "qualite_nonconformite") }}