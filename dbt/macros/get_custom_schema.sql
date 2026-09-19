{# dbt's default behaviour concatenates the target schema and a model's
   custom +schema config ("analytics_staging", "analytics_marts"). Overriding
   this to just use the custom schema directly keeps `staging`/`marts` as
   the actual Postgres schema names, matching how the rest of this repo
   (raw.*) names schemas. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
