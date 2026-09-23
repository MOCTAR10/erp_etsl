select
    now()::date as as_of_date,
    -- ASMR : disponibilite materielle (maintenance).
    (select count(distinct id) from {{ ref("stg_erp_maintenance") }}) as asmr_equipements,
    (select count(distinct id) from {{ ref("stg_erp_maintenance") }} where is_operationnel) as asmr_operationnels,
    (select count(distinct id) from {{ ref("stg_erp_maintenance") }} where is_en_arret) as asmr_en_arret,
    -- HSE.
    (select count(distinct id) from {{ ref("stg_erp_hse") }}) as hse_incidents_total,
    (select count(*) from {{ ref("stg_erp_hse") }} where not is_cloture) as hse_incidents_ouverts,
    (select count(*) from {{ ref("stg_erp_hse") }} where is_accident) as hse_accidents,
    -- Qualite.
    (select count(distinct id) from {{ ref("stg_erp_qualite") }}) as nc_total,
    (select count(*) from {{ ref("stg_erp_qualite") }} where not is_cloture) as nc_ouvertes,
    (select count(*) from {{ ref("stg_erp_qualite") }} where is_critique and not is_cloture) as nc_critiques