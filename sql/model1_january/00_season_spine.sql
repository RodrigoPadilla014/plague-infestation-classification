/*
Model 1 January v1: season-aware spine and target contract.

Grain:
  one row per (lot_key, target_rainy_year)

Target:
  target_plague_gt_050_clean = 1 when any valid nymph observation in the
  lot-season exceeds 0.50 nymphs/stem.

Target QA:
  Observations flagged flag_ninfas_posible_error_muestreo are ignored for
  target construction. If no valid nymph observation remains, the row is
  target_unknown and must be excluded from v1 training.

This query is the base table for all Model 1 January feature-family joins.
*/

WITH eligible_observations AS (
    SELECT
        c.record_id,
        c.source_row,
        c.zafra AS plague_zafra,
        replace(c.zafra, '/', '_') AS plague_zafra_norm,
        c.ingenio,
        c.mill_name,
        c.environmental_lot_key AS lot_key,
        c.productivity_lot_key,
        c.fecha::date AS visit_date,
        extract(year FROM c.fecha)::integer AS visit_year,
        extract(month FROM c.fecha)::integer AS visit_month,
        c.ninfas_tallo,
        c.adultos_tallo,
        c.qa_status,
        c.flag_ninfas_posible_error_muestreo,
        c.flag_ninfas_extremo,
        c.flag_ninfas_outlier,
        c.flag_fecha_sospechosa,
        c.flag_lote_cero_extra_ambiguo,
        c.flag_lote_posible_cero_extra,
        CASE
            WHEN c.fecha IS NULL THEN NULL
            WHEN extract(month FROM c.fecha)::integer BETWEEN 5 AND 10
                THEN extract(year FROM c.fecha)::integer
            WHEN extract(month FROM c.fecha)::integer BETWEEN 11 AND 12
                THEN extract(year FROM c.fecha)::integer
            WHEN extract(month FROM c.fecha)::integer BETWEEN 1 AND 4
                THEN extract(year FROM c.fecha)::integer
            ELSE NULL
        END AS target_rainy_year,
        CASE
            WHEN c.fecha IS NULL THEN 'missing_date'
            WHEN extract(month FROM c.fecha)::integer BETWEEN 5 AND 10
                THEN 'rainy_core_may_oct'
            WHEN extract(month FROM c.fecha)::integer BETWEEN 11 AND 12
                THEN 'late_nov_dec_review'
            WHEN extract(month FROM c.fecha)::integer BETWEEN 1 AND 4
                THEN 'early_jan_apr_review'
            ELSE 'review'
        END AS target_year_rule
    FROM public.chinche c
    WHERE c.environmental_lot_key IS NOT NULL
      AND c.productivity_lot_key IS NOT NULL
      AND c.zafra IS NOT NULL
      AND NOT c.flag_duplicado_exacto
),

season_spine AS (
    SELECT
        lot_key,
        target_rainy_year,
        min(productivity_lot_key) AS productivity_lot_key,
        min(ingenio) AS ingenio,
        min(mill_name) AS mill_name,
        string_agg(DISTINCT plague_zafra, ', ' ORDER BY plague_zafra) AS plague_zafras,
        count(*) AS n_observations,
        count(*) FILTER (WHERE target_year_rule = 'rainy_core_may_oct')
            AS n_core_rainy_observations,
        count(*) FILTER (WHERE target_year_rule <> 'rainy_core_may_oct')
            AS n_edge_month_observations,
        min(visit_date) AS first_visit,
        max(visit_date) AS last_visit,
        count(*) FILTER (WHERE ninfas_tallo IS NOT NULL) AS n_nymph_observations_raw,
        count(*) FILTER (
            WHERE ninfas_tallo IS NOT NULL
              AND NOT flag_ninfas_posible_error_muestreo
        ) AS n_valid_nymph_observations,
        max(ninfas_tallo) AS target_max_ninfas_raw,
        max(ninfas_tallo) FILTER (
            WHERE NOT flag_ninfas_posible_error_muestreo
        ) AS target_max_valid_ninfas,
        (max(ninfas_tallo) > 0.50)::integer AS target_plague_gt_050_raw,
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
        END AS target_plague_gt_050_clean,
        CASE
            WHEN count(*) FILTER (
                WHERE ninfas_tallo IS NOT NULL
                  AND NOT flag_ninfas_posible_error_muestreo
            ) = 0 THEN 'unknown_no_valid_nymph_observation'
            WHEN bool_or(
                ninfas_tallo > 0.50
                AND NOT flag_ninfas_posible_error_muestreo
            ) THEN 'clean_positive'
            WHEN count(*) FILTER (WHERE flag_ninfas_posible_error_muestreo) > 0
                THEN 'clean_negative_with_suspicious_measurement'
            ELSE 'clean_negative'
        END AS target_status,
        (
            count(*) FILTER (
                WHERE ninfas_tallo IS NOT NULL
                  AND NOT flag_ninfas_posible_error_muestreo
            ) > 0
        ) AS target_trainable,
        count(*) FILTER (WHERE ninfas_tallo > 0.50) AS n_obs_gt_050_raw,
        count(*) FILTER (
            WHERE ninfas_tallo > 0.50
              AND NOT flag_ninfas_posible_error_muestreo
        ) AS n_valid_obs_gt_050,
        count(*) FILTER (WHERE flag_ninfas_posible_error_muestreo)
            AS n_possible_sampling_error,
        count(*) FILTER (WHERE flag_ninfas_extremo) AS n_extreme_ninfas,
        count(*) FILTER (WHERE flag_ninfas_outlier) AS n_ninfas_outlier,
        bool_or(flag_fecha_sospechosa) AS has_suspicious_date,
        bool_or(flag_lote_cero_extra_ambiguo) AS has_ambiguous_lot_zero,
        bool_or(flag_lote_posible_cero_extra) AS has_possible_lot_zero,
        string_agg(DISTINCT target_year_rule, ', ' ORDER BY target_year_rule)
            AS target_year_rules
    FROM eligible_observations
    WHERE target_rainy_year IS NOT NULL
    GROUP BY lot_key, target_rainy_year
)

SELECT *
FROM season_spine
WHERE target_rainy_year <> 2021
ORDER BY target_rainy_year, lot_key;
