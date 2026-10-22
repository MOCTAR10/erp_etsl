-- Budgets M11 (Couche D) : type, exercice, axe / compte analytique, classe du mix, statut.
select
    id,
    code,
    type_budget,
    fiscal_year_id,
    axis_id,
    analytic_id,
    montant,
    statut,
    classe_mix,
    (statut in ('approuve', 'cloture')) as is_approuve
from {{ source("etls_replica", "controle_gestion_budget") }}
