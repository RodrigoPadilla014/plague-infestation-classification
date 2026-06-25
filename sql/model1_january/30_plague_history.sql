/*
Model 1 January v1: lagged plague history feature family.

Requires temp view:
  season_spine

History is based on the same clean target policy as the v1 spine and uses
strictly prior target_rainy_year values.
*/

WITH observation_targets AS (
    SELECT
        c.environmental_lot_key AS lot_key,
        extract(year FROM c.fecha)::integer AS target_rainy_year,
        c.ninfas_tallo,
        c.flag_ninfas_posible_error_muestreo
    FROM public.chinche c
    WHERE c.environmental_lot_key IS NOT NULL
      AND c.fecha IS NOT NULL
      AND c.zafra IS NOT NULL
      AND NOT c.flag_duplicado_exacto
      AND extract(month FROM c.fecha)::integer BETWEEN 5 AND 10
),

lot_year_targets AS (
    SELECT
        lot_key,
        target_rainy_year,
        CASE
            WHEN count(*) FILTER (
                WHERE ninfas_tallo IS NOT NULL
                  AND NOT flag_ninfas_posible_error_muestreo
            ) = 0 THEN NULL
            WHEN bool_or(
                ninfas_tallo > 0.50
                AND NOT flag_ninfas_posible_error_muestreo
            ) THEN 1
            ELSE 0
        END AS clean_target,
        max(ninfas_tallo) FILTER (
            WHERE NOT flag_ninfas_posible_error_muestreo
        ) AS max_valid_ninfas
    FROM observation_targets
    GROUP BY
        lot_key,
        target_rainy_year
)

SELECT
    s.lot_key,
    s.target_rainy_year,
    max(h.clean_target) FILTER (
        WHERE h.target_rainy_year = s.target_rainy_year - 1
    ) AS plague_prev_year,
    sum(h.clean_target) FILTER (
        WHERE h.target_rainy_year >= s.target_rainy_year - 3
          AND h.target_rainy_year < s.target_rainy_year
    ) AS plague_count_last3,
    count(h.clean_target) FILTER (
        WHERE h.target_rainy_year >= s.target_rainy_year - 3
          AND h.target_rainy_year < s.target_rainy_year
    ) AS plague_known_years_last3,
    sum(h.clean_target) AS plague_count_all_prior,
    count(h.clean_target) AS plague_known_years_all_prior,
    avg(h.max_valid_ninfas) AS plague_prior_mean_max_valid_ninfas,
    max(h.max_valid_ninfas) AS plague_prior_max_valid_ninfas
FROM season_spine s
LEFT JOIN lot_year_targets h
    ON h.lot_key = s.lot_key
   AND h.target_rainy_year < s.target_rainy_year
GROUP BY
    s.lot_key,
    s.target_rainy_year
ORDER BY
    s.target_rainy_year,
    s.lot_key;
