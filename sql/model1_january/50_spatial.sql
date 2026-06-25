/*
Model 1 January v1: spatial coordinate feature family.

Requires temp view:
  season_spine
*/

SELECT
    s.lot_key,
    s.target_rainy_year,
    sp.shape_year AS spatial_shape_year,
    sp.centroid_lon AS spatial_centroid_lon,
    sp.centroid_lat AS spatial_centroid_lat,
    sp.area_ha_dissolved AS spatial_area_ha_dissolved,
    sp.perimeter_m_dissolved AS spatial_perimeter_m_dissolved,
    sp.geometry_valid AS spatial_geometry_valid,
    sp.geometry_empty AS spatial_geometry_empty,
    (sp.environmental_lot_key IS NOT NULL) AS spatial_has_record
FROM season_spine s
LEFT JOIN LATERAL (
    SELECT sp.*
    FROM public.spatial_lot_year_slim sp
    WHERE sp.environmental_lot_key = s.lot_key
      AND sp.shape_year <= s.target_rainy_year
    ORDER BY
        CASE WHEN sp.shape_year = s.target_rainy_year THEN 0 ELSE 1 END,
        sp.shape_year DESC
    LIMIT 1
) sp ON true
ORDER BY
    s.target_rainy_year,
    s.lot_key;
