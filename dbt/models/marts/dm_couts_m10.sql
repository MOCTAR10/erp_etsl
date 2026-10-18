-- Couts et produits M10 (Couche D) : grand livre comptabilise, par mois et par compte analytique.
-- Meme regle que controle_gestion.services.compute_marges : ecritures POSTED et REVERSED (une extourne s'annule
-- en net), produits = credit - debit (classe 7), charges = debit - credit (classe 6) HORS 618, cout GLOBAL RENTAL
-- (compte 618000) isole.
select
    to_char(m.date, 'YYYY-MM') as periode,
    ax.axis_type,
    aa.code as analytique_code,
    aa.label as analytique_libelle,
    coalesce(sum(l.credit - l.debit) filter (where a.account_type = 'income'), 0) as produits,
    coalesce(sum(l.debit - l.credit) filter (where a.account_type = 'expense' and a.code <> '618000'), 0) as charges,
    coalesce(sum(l.debit - l.credit) filter (where a.code = '618000'), 0) as cout_gr,
    current_date as as_of_date
from {{ source("etls_replica", "accounting_kernel_accountmoveline") }} l
join {{ source("etls_replica", "accounting_kernel_accountmove") }} m on m.id = l.move_id
join {{ source("etls_replica", "referentiels_account") }} a on a.id = l.account_id
left join {{ source("etls_replica", "referentiels_analyticaccount") }} aa on aa.id = l.analytic_account_id
left join {{ source("etls_replica", "referentiels_analyticaxis") }} ax on ax.id = aa.axis_id
where m.status in ('posted', 'reversed')
  and a.account_class in (6, 7)
group by 1, 2, 3, 4
