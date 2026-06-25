/*
Model 1 January v1: final feature dataset assembly.

Requires temp views:
  season_spine
  enso_forecast_features
  historical_rainy_climate_features
  plague_history_features
  static_productividad_features
  spatial_features
*/

SELECT
    -- Metadata and target audit columns.
    s.lot_key,
    s.productivity_lot_key,
    s.target_rainy_year,
    s.plague_zafras,
    s.ingenio,
    s.mill_name,
    s.first_visit,
    s.last_visit,
    s.n_observations,
    s.n_core_rainy_observations,
    s.n_edge_month_observations,
    s.n_nymph_observations_raw,
    s.n_valid_nymph_observations,
    s.target_max_ninfas_raw,
    s.target_max_valid_ninfas,
    s.target_plague_gt_050_raw,
    s.target_plague_gt_050_clean AS target,
    s.target_status,
    s.n_possible_sampling_error,
    s.n_extreme_ninfas,
    s.n_ninfas_outlier,
    s.target_year_rules,

    -- ENSO forecast and January state.
    e.enso_amj_la_nina_pct,
    e.enso_amj_neutral_pct,
    e.enso_amj_el_nino_pct,
    e.enso_mjj_la_nina_pct,
    e.enso_mjj_neutral_pct,
    e.enso_mjj_el_nino_pct,
    e.enso_jja_la_nina_pct,
    e.enso_jja_neutral_pct,
    e.enso_jja_el_nino_pct,
    e.enso_jas_la_nina_pct,
    e.enso_jas_neutral_pct,
    e.enso_jas_el_nino_pct,
    e.enso_aso_la_nina_pct,
    e.enso_aso_neutral_pct,
    e.enso_aso_el_nino_pct,
    e.enso_jan_oni,
    e.enso_jan_nino34,
    e.enso_jan_soi,
    e.enso_jan_mei,
    e.enso_jan_pdo,
    e.enso_jan_amo,

    -- Historical rainy-season climate suitability.
    c.hist_rainy_year_count,
    c.hist_rainy_pentad_count,
    c.hist_rainy_precip_sum_mm_mean,
    c.hist_rainy_precip_sum_mm_min,
    c.hist_rainy_precip_sum_mm_max,
    c.hist_rainy_eto_sum_mm_mean,
    c.hist_rainy_temp_mean_c_mean,
    c.hist_rainy_temp_max_c_mean,
    c.hist_rainy_temp_min_c_mean,
    c.hist_rainy_relative_humidity_pct_mean,
    c.hist_rainy_radiation_sum_mean,
    c.hist_rainy_heat_index_max_mean,
    c.hist_rainy_leaf_wetness_mean_mean,

    -- Lagged plague history.
    h.plague_prev_year,
    h.plague_count_last3,
    h.plague_known_years_last3,
    h.plague_count_all_prior,
    h.plague_known_years_all_prior,
    h.plague_prior_mean_max_valid_ninfas,
    h.plague_prior_max_valid_ninfas,

    -- Static/productividad and crop timing context.
    p.prod_source_zafra,
    p.prod_cierre_date,
    p.crop_start_date,
    p.crop_age_days_jun_01,
    p.crop_age_days_jul_01,
    p.crop_age_days_aug_01,
    p.crop_age_days_sep_01,
    p.crop_age_days_oct_01,
    p.prod_variedad,
    p.prod_grupo_de_suelo,
    p.prod_familia_de_suelo,
    p.prod_grupo_de_humedad,
    p.prod_area_ha,
    p.prod_no_corte,
    p.prod_codigo_zae,
    p.prod_estrato,
    p.prod_has_record_by_jan31,

    -- Spatial coordinates.
    sp.spatial_shape_year,
    sp.spatial_centroid_lon,
    sp.spatial_centroid_lat,
    sp.spatial_area_ha_dissolved,
    sp.spatial_perimeter_m_dissolved,
    sp.spatial_geometry_valid,
    sp.spatial_geometry_empty,
    sp.spatial_has_record
FROM season_spine s
LEFT JOIN enso_forecast_features e
    ON e.lot_key = s.lot_key
   AND e.target_rainy_year = s.target_rainy_year
LEFT JOIN historical_rainy_climate_features c
    ON c.lot_key = s.lot_key
   AND c.target_rainy_year = s.target_rainy_year
LEFT JOIN plague_history_features h
    ON h.lot_key = s.lot_key
   AND h.target_rainy_year = s.target_rainy_year
LEFT JOIN static_productividad_features p
    ON p.lot_key = s.lot_key
   AND p.target_rainy_year = s.target_rainy_year
LEFT JOIN spatial_features sp
    ON sp.lot_key = s.lot_key
   AND sp.target_rainy_year = s.target_rainy_year
WHERE s.target_trainable
ORDER BY
    s.target_rainy_year,
    s.lot_key;
