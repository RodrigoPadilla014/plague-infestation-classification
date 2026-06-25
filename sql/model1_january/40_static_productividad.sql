/*
Model 1 January v1: static productividad feature family.

Requires temp view:
  season_spine

Chooses the latest productividad record for the lot with cierre known by
Jan 31 of the target rainy year. Outcome and operation fields are excluded.
*/

SELECT
    s.lot_key,
    s.target_rainy_year,
    p.zafra AS prod_source_zafra,
    p.cierre_date AS prod_cierre_date,
    (p.cierre_date + interval '1 day')::date AS crop_start_date,
    (make_date(s.target_rainy_year, 6, 1) - (p.cierre_date + interval '1 day')::date)
        AS crop_age_days_jun_01,
    (make_date(s.target_rainy_year, 7, 1) - (p.cierre_date + interval '1 day')::date)
        AS crop_age_days_jul_01,
    (make_date(s.target_rainy_year, 8, 1) - (p.cierre_date + interval '1 day')::date)
        AS crop_age_days_aug_01,
    (make_date(s.target_rainy_year, 9, 1) - (p.cierre_date + interval '1 day')::date)
        AS crop_age_days_sep_01,
    (make_date(s.target_rainy_year, 10, 1) - (p.cierre_date + interval '1 day')::date)
        AS crop_age_days_oct_01,
    p.variedad AS prod_variedad,
    p.grupo_de_suelo AS prod_grupo_de_suelo,
    p.familia_de_suelo AS prod_familia_de_suelo,
    p.grupo_de_humedad AS prod_grupo_de_humedad,
    p.area AS prod_area_ha,
    p.no_corte AS prod_no_corte,
    p.codigo_zae AS prod_codigo_zae,
    p.estrato AS prod_estrato,
    (p.lote IS NOT NULL) AS prod_has_record_by_jan31
FROM season_spine s
LEFT JOIN LATERAL (
    SELECT
        p.*,
        to_date(p.cierre, 'YYYY-MM-DD') AS cierre_date
    FROM public.productividad p
    WHERE p.lote = s.productivity_lot_key
      AND p.cierre ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      AND to_date(p.cierre, 'YYYY-MM-DD') >= date '2000-01-01'
      AND to_date(p.cierre, 'YYYY-MM-DD') <= make_date(s.target_rainy_year, 1, 31)
    ORDER BY to_date(p.cierre, 'YYYY-MM-DD') DESC
    LIMIT 1
) p ON true
ORDER BY
    s.target_rainy_year,
    s.lot_key;
