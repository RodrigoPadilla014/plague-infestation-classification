/*
Model 1 January diagnostics: season-aware spine and target.

Purpose:
  Diagnose whether the v1 dataset should use (lot_key, target_rainy_year)
  instead of raw plague zafra labels.

This query does not create a training dataset. It keeps target variants and
QA counts side by side so the target contract can be approved before feature
implementation.
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
        c.flag_duplicado_exacto,
        c.flag_ninfas_posible_error_muestreo,
        c.flag_ninfas_extremo,
        c.flag_ninfas_outlier,
        c.flag_fecha_faltante,
        c.flag_fecha_sospechosa,
        c.flag_zafra_faltante,
        c.flag_lote_cero_extra_ambiguo,
        c.flag_lote_posible_cero_extra,
        CASE
            WHEN c.fecha IS NULL THEN NULL
            /*
             * The observed pest season is primarily May-Oct. For these rows,
             * the rainy-season target year is the visit calendar year.
             *
             * Nov-Dec and Jan-Apr are kept but flagged downstream because they
             * may belong to carryover, late/early sampling, or source-label
             * ambiguity depending on mill practice.
             */
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
        count(*) FILTER (WHERE target_year_rule = 'rainy_core_may_oct') AS n_core_rainy_observations,
        count(*) FILTER (WHERE target_year_rule <> 'rainy_core_may_oct') AS n_edge_month_observations,
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
        count(*) FILTER (WHERE flag_ninfas_posible_error_muestreo) AS n_possible_sampling_error,
        count(*) FILTER (WHERE flag_ninfas_extremo) AS n_extreme_ninfas,
        count(*) FILTER (WHERE flag_ninfas_outlier) AS n_ninfas_outlier,
        count(*) FILTER (WHERE qa_status IN ('review', 'duplicate')) AS n_review_or_duplicate_status,
        bool_or(flag_fecha_sospechosa) AS has_suspicious_date,
        bool_or(flag_lote_cero_extra_ambiguo) AS has_ambiguous_lot_zero,
        bool_or(flag_lote_posible_cero_extra) AS has_possible_lot_zero,
        string_agg(DISTINCT target_year_rule, ', ' ORDER BY target_year_rule) AS target_year_rules
    FROM eligible_observations
    WHERE target_rainy_year IS NOT NULL
    GROUP BY lot_key, target_rainy_year
),

with_enso AS (
    SELECT
        s.*,
        (count(f.*) FILTER (
            WHERE f.target_season IN ('AMJ', 'MJJ', 'JJA', 'JAS', 'ASO')
        ) = 5) AS has_core_enso_forecast,
        max(e.oni) AS enso_oni_january,
        max(e.nino34) AS enso_nino34_january,
        max(e.soi) AS enso_soi_january,
        max(e.mei) AS enso_mei_january
    FROM season_spine s
    LEFT JOIN public.enso_january_forecast f
        ON f.forecast_year = s.target_rainy_year
    LEFT JOIN public.enso e
        ON e.year = s.target_rainy_year
       AND e.month = 1
    GROUP BY
        s.lot_key,
        s.target_rainy_year,
        s.productivity_lot_key,
        s.ingenio,
        s.mill_name,
        s.plague_zafras,
        s.n_observations,
        s.n_core_rainy_observations,
        s.n_edge_month_observations,
        s.first_visit,
        s.last_visit,
        s.n_nymph_observations_raw,
        s.n_valid_nymph_observations,
        s.target_max_ninfas_raw,
        s.target_max_valid_ninfas,
        s.target_plague_gt_050_raw,
        s.target_plague_gt_050_clean,
        s.target_status,
        s.target_trainable,
        s.n_obs_gt_050_raw,
        s.n_valid_obs_gt_050,
        s.n_possible_sampling_error,
        s.n_extreme_ninfas,
        s.n_ninfas_outlier,
        s.n_review_or_duplicate_status,
        s.has_suspicious_date,
        s.has_ambiguous_lot_zero,
        s.has_possible_lot_zero,
        s.target_year_rules
),

join_diagnostics AS (
    SELECT
        e.*,
        /*
         * Climate zafra labels run Nov-Oct. A target rainy year Y maps to
         * climate zafra (Y-1)_Y for Jun-Oct climate rows.
         */
        ((e.target_rainy_year - 1)::text || '_' || e.target_rainy_year::text)
            AS climate_zafra_for_target,
        EXISTS (
            SELECT 1
            FROM public.clima_lote_pentada_new cl
            WHERE cl.cod_cg = e.lot_key
              AND cl.zafra = ((e.target_rainy_year - 1)::text || '_' || e.target_rainy_year::text)
              AND cl.mes BETWEEN 6 AND 10
        ) AS has_target_year_rainy_climate,
        EXISTS (
            SELECT 1
            FROM public.clima_lote_pentada_new cl
            WHERE cl.cod_cg = e.lot_key
              AND cl.mes BETWEEN 6 AND 10
              AND cl.fecha_inicio < make_date(e.target_rainy_year, 1, 1)
        ) AS has_prior_rainy_climate_history,
        EXISTS (
            SELECT 1
            FROM public.productividad p
            WHERE p.lote = e.productivity_lot_key
        ) AS has_any_productividad,
        EXISTS (
            SELECT 1
            FROM public.productividad p
            WHERE p.lote = e.productivity_lot_key
              AND p.zafra = ((e.target_rainy_year - 1)::text || '-' || e.target_rainy_year::text)
        ) AS has_same_label_productividad,
        EXISTS (
            SELECT 1
            FROM public.spatial_lot_year_slim sp
            WHERE sp.environmental_lot_key = e.lot_key
        ) AS has_any_spatial,
        EXISTS (
            SELECT 1
            FROM public.spatial_lot_year_slim sp
            WHERE sp.environmental_lot_key = e.lot_key
              AND sp.shape_year = e.target_rainy_year
        ) AS has_same_year_spatial
    FROM with_enso e
)

SELECT *
FROM join_diagnostics
ORDER BY target_rainy_year, lot_key;
