/*
Model 1 January v1: ENSO forecast feature family.

Requires temp view:
  season_spine

Grain:
  one row per (lot_key, target_rainy_year)
*/

SELECT
    s.lot_key,
    s.target_rainy_year,

    max(f.la_nina_pct) FILTER (WHERE f.target_season = 'AMJ') AS enso_amj_la_nina_pct,
    max(f.neutral_pct) FILTER (WHERE f.target_season = 'AMJ') AS enso_amj_neutral_pct,
    max(f.el_nino_pct) FILTER (WHERE f.target_season = 'AMJ') AS enso_amj_el_nino_pct,

    max(f.la_nina_pct) FILTER (WHERE f.target_season = 'MJJ') AS enso_mjj_la_nina_pct,
    max(f.neutral_pct) FILTER (WHERE f.target_season = 'MJJ') AS enso_mjj_neutral_pct,
    max(f.el_nino_pct) FILTER (WHERE f.target_season = 'MJJ') AS enso_mjj_el_nino_pct,

    max(f.la_nina_pct) FILTER (WHERE f.target_season = 'JJA') AS enso_jja_la_nina_pct,
    max(f.neutral_pct) FILTER (WHERE f.target_season = 'JJA') AS enso_jja_neutral_pct,
    max(f.el_nino_pct) FILTER (WHERE f.target_season = 'JJA') AS enso_jja_el_nino_pct,

    max(f.la_nina_pct) FILTER (WHERE f.target_season = 'JAS') AS enso_jas_la_nina_pct,
    max(f.neutral_pct) FILTER (WHERE f.target_season = 'JAS') AS enso_jas_neutral_pct,
    max(f.el_nino_pct) FILTER (WHERE f.target_season = 'JAS') AS enso_jas_el_nino_pct,

    max(f.la_nina_pct) FILTER (WHERE f.target_season = 'ASO') AS enso_aso_la_nina_pct,
    max(f.neutral_pct) FILTER (WHERE f.target_season = 'ASO') AS enso_aso_neutral_pct,
    max(f.el_nino_pct) FILTER (WHERE f.target_season = 'ASO') AS enso_aso_el_nino_pct,

    max(e.oni) AS enso_jan_oni,
    max(e.nino34) AS enso_jan_nino34,
    max(e.soi) AS enso_jan_soi,
    max(e.mei) AS enso_jan_mei,
    max(e.pdo) AS enso_jan_pdo,
    max(e.amo) AS enso_jan_amo,

    (count(f.*) FILTER (
        WHERE f.target_season IN ('AMJ', 'MJJ', 'JJA', 'JAS', 'ASO')
    ) = 5) AS enso_has_core_forecast_windows
FROM season_spine s
LEFT JOIN public.enso_january_forecast f
    ON f.forecast_year = s.target_rainy_year
LEFT JOIN public.enso e
    ON e.year = s.target_rainy_year
   AND e.month = 1
GROUP BY
    s.lot_key,
    s.target_rainy_year
ORDER BY
    s.target_rainy_year,
    s.lot_key;
