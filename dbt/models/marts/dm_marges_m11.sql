-- Marges M11 par affaire et par mois (Couche D) : grand livre comptabilise (POSTED et REVERSED) impute au compte
-- analytique de l'affaire (commercial_affaire.analytic_id). Meme regle que controle_gestion.services.compute_marges :
-- produits = credit - debit (classe 7), charges = debit - credit (classe 6) HORS 618, cout GLOBAL RENTAL isole ;
-- marge = produits - charges - cout_gr.
with lignes as (
    select
        to_char(m.date, 'YYYY-MM') as periode,
        l.analytic_account_id,
        coalesce(sum(l.credit - l.debit) filter (where a.account_type = 'income'), 0) as produits,
        coalesce(sum(l.debit - l.credit) filter (where a.account_type = 'expense' and a.code <> '618000'), 0) as charges,
        coalesce(sum(l.debit - l.credit) filter (where a.code = '618000'), 0) as cout_gr
    from {{ source("etls_replica", "accounting_kernel_accountmoveline") }} l
    join {{ source("etls_replica", "accounting_kernel_accountmove") }} m on m.id = l.move_id
    join {{ source("etls_replica", "referentiels_account") }} a on a.id = l.account_id
    where m.status in ('posted', 'reversed')
      and a.account_class in (6, 7)
      and l.analytic_account_id is not null
    group by 1, 2
)
select
    l.periode,
    af.id as affaire_id,
    af.code as affaire_code,
    af.title as affaire_libelle,
    af.affaire_type,
    af.is_global_rental,
    aa.code as analytique_code,
    l.produits,
    l.charges,
    l.cout_gr,
    l.produits - l.charges - l.cout_gr as marge,
    case when l.produits <> 0 then round((l.produits - l.charges - l.cout_gr) * 100 / l.produits, 2) end as taux_marge_pct,
    current_date as as_of_date
from lignes l
join {{ source("etls_replica", "commercial_affaire") }} af on af.analytic_id = l.analytic_account_id
join {{ source("etls_replica", "referentiels_analyticaccount") }} aa on aa.id = l.analytic_account_id
