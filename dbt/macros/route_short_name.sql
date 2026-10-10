{#
  Route number from a Translink route_id ("412-5065" -> "412", "BRBN-5185" ->
  "BRBN"). The suffix is the timetable version, and the static feed only holds
  the current versions, so joining live data on the full route_id drops every
  observation made under an older timetable: two-thirds of stop visits after
  the 10 Oct reload. Join live data to routes on this instead.
#}
{% macro route_short_name(route_id) -%}
    regexp_replace({{ route_id }}, '-[^-]*$', '')
{%- endmacro %}
