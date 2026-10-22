{#
  Schémas fixes `staging` et `marts` (et non `<cible>_staging`) : l'ERP (analytics.pilotage._lire_mart,
  analytics.bi_etat.fraicheur_couche_d) et Superset lisent `marts.<mart>`.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
