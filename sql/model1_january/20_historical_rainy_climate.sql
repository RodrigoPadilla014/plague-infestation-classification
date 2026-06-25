/*
Model 1 January v1: historical rainy-season climate feature family.

Requires temp view:
  season_spine

Uses only Jun-Oct climate rows from calendar years strictly before the
target_rainy_year, then averages prior rainy-season annual summaries.
*/

WITH spine_lots AS (
    SELECT DISTINCT lot_key
    FROM season_spine
),

climate_annual AS (
    SELECT
        cl.cod_cg AS lot_key,
        extract(year FROM cl.fecha_inicio)::integer AS climate_year,
        count(*) AS hist_rainy_pentads,
        sum(cl.precipitacion_sum) AS annual_rainy_precip_sum_mm,
        sum(cl.eto_sum) AS annual_rainy_eto_sum_mm,
        avg(cl.temperatura_mean) AS annual_rainy_temp_mean_c,
        avg(cl.temperatura_max) AS annual_rainy_temp_max_c,
        avg(cl.temperatura_min) AS annual_rainy_temp_min_c,
        avg(cl.humedad_relativa) AS annual_rainy_relative_humidity_pct,
        sum(cl.radiacion_sum) AS annual_rainy_radiation_sum,
        max(cl.indice_calor_max) AS annual_rainy_heat_index_max,
        avg(cl.mojadura_mean) AS annual_rainy_leaf_wetness_mean
    FROM public.clima_lote_pentada_new cl
    INNER JOIN spine_lots sl
        ON sl.lot_key = cl.cod_cg
    WHERE cl.mes BETWEEN 6 AND 10
    GROUP BY
        cl.cod_cg,
        extract(year FROM cl.fecha_inicio)::integer
),

prior_rainy_years AS (
    SELECT
        s.lot_key,
        s.target_rainy_year,
        ca.climate_year,
        ca.hist_rainy_pentads,
        ca.annual_rainy_precip_sum_mm,
        ca.annual_rainy_eto_sum_mm,
        ca.annual_rainy_temp_mean_c,
        ca.annual_rainy_temp_max_c,
        ca.annual_rainy_temp_min_c,
        ca.annual_rainy_relative_humidity_pct,
        ca.annual_rainy_radiation_sum,
        ca.annual_rainy_heat_index_max,
        ca.annual_rainy_leaf_wetness_mean
    FROM season_spine s
    LEFT JOIN climate_annual ca
        ON ca.lot_key = s.lot_key
       AND ca.climate_year < s.target_rainy_year
)

SELECT
    lot_key,
    target_rainy_year,
    count(climate_year) AS hist_rainy_year_count,
    sum(hist_rainy_pentads) AS hist_rainy_pentad_count,

    avg(annual_rainy_precip_sum_mm) AS hist_rainy_precip_sum_mm_mean,
    min(annual_rainy_precip_sum_mm) AS hist_rainy_precip_sum_mm_min,
    max(annual_rainy_precip_sum_mm) AS hist_rainy_precip_sum_mm_max,

    avg(annual_rainy_eto_sum_mm) AS hist_rainy_eto_sum_mm_mean,
    avg(annual_rainy_temp_mean_c) AS hist_rainy_temp_mean_c_mean,
    avg(annual_rainy_temp_max_c) AS hist_rainy_temp_max_c_mean,
    avg(annual_rainy_temp_min_c) AS hist_rainy_temp_min_c_mean,
    avg(annual_rainy_relative_humidity_pct) AS hist_rainy_relative_humidity_pct_mean,
    avg(annual_rainy_radiation_sum) AS hist_rainy_radiation_sum_mean,
    avg(annual_rainy_heat_index_max) AS hist_rainy_heat_index_max_mean,
    avg(annual_rainy_leaf_wetness_mean) AS hist_rainy_leaf_wetness_mean_mean
FROM prior_rainy_years
GROUP BY
    lot_key,
    target_rainy_year
ORDER BY
    target_rainy_year,
    lot_key;
