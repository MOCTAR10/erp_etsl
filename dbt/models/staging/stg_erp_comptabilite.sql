-- Écritures comptabilisées M10 (Couche D) : lignes des pièces validées (brouillons exclus), compte SYSCOHADA,
-- analytique ; le compte 618 (GLOBAL RENTAL) est signalé pour rester isolé des charges.
select
    l.id,
    m.id as move_id,
    m.number,
    m.date,
    m.status,
    m.source,
    a.code as account_code,
    l.analytic_account_id,
    l.debit,
    l.credit,
    (a.code like '618%') as is_global_rental
from {{ source("etls_replica", "accounting_kernel_accountmoveline") }} l
join {{ source("etls_replica", "accounting_kernel_accountmove") }} m on m.id = l.move_id
join {{ source("etls_replica", "referentiels_account") }} a on a.id = l.account_id
where m.status in ('posted', 'reversed')
