# Model 1 January Feature Recipe

Purpose: build the first real ML dataset for January seasonal risk ranking.

The model asks:

```text
Given January-available season context, historical rainy-season suitability,
lot vulnerability, and prior plague pressure, which lots are most likely to
show infestation during the target rainy season?
```

## Grain

One row per:

```text
lot_key, target_rainy_year
```

`target_rainy_year` is the calendar year of the rainy-season infestation period
being predicted. For core May-Oct plague observations, it is the visit calendar
year.

## Target

Training target:

```text
target_plague_gt_050_clean
```

Rules:

- exact duplicates are excluded;
- rows flagged `flag_ninfas_posible_error_muestreo` are ignored for target
  construction;
- if any valid `ninfas_tallo > 0.50`, target is `1`;
- if valid observations exist and all are `<= 0.50`, target is `0`;
- if no valid nymph observation remains, target is unknown and excluded from
  v1 training.

## Files

- `00_season_spine.sql` — official season-aware spine and target contract
- `10_enso_forecast.sql` — ENSO forecast feature family
- `20_historical_rainy_climate.sql` — historical Jun-Oct climate suitability
- `30_plague_history.sql` — strictly lagged plague history
- `40_static_productividad.sql` — safe static lot/productividad fields
- `50_spatial.sql` — coordinates and spatial size features
- `90_final_dataset.sql` — final feature-family assembly
- `diagnostics/` — exploratory SQL used to approve or audit the recipe

## Current Status

The first full dataset has been produced:

```text
data/ml_dataset_model1_january_v001.parquet
data/ml_dataset_model1_january_v001.manifest.json
```

Summary:

- rows: 4,185
- columns: 88
- clean positives: 838
- clean negatives: 3,347
- target years: 2019, 2020, 2023, 2024, 2025

Build command:

```powershell
python scripts/build_dataset.py --recipe model1_january --version v001
```
