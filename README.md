# Sugarcane Stink Bug Infestation Classifier

A binary probabilistic classifier that predicts *Aeneolamia postica* (sugarcane stink bug) infestation in Guatemalan sugar mills at the lot level, one full growing season ahead of harvest.

## Problem

Sugarcane stink bugs cause significant crop losses in Guatemala. Entomologists sample lots throughout the rainy season, but field campaigns are expensive. The goal is to predict, at the start of January (before the rainy season begins), which lots are at high risk of infestation — so resources can be targeted where they matter most.

Missing an outbreak is far more costly than a false alarm, so the primary metric is **recall**, constrained to 0.85 minimum.

## Approach

- **Target**: binary label — whether a lot exceeds the infestation threshold during the upcoming rainy season
- **Prediction horizon**: January, before the rainy season (no in-season data at prediction time)
- **Cross-validation**: expanding walk-forward by `zafra` (rainy year) to respect time order and prevent leakage
- **Models**: LightGBM, XGBoost, CatBoost — evaluated in parallel, native categorical support
- **Hyperparameter tuning**: Optuna with a stability penalty (optimizes mean minus std across folds, not just mean)
- **Calibration**: isotonic or sigmoid regression on out-of-fold predictions
- **Threshold**: selected to satisfy the recall constraint on the most recent held-out period
- **Explainability**: SHAP feature importance logged per fold and aggregated

## Feature Groups

Features are built from historical data available before the prediction date:

| Group | Examples |
|---|---|
| ENSO forecast | ONI index, La Nina probability |
| Historical climate | Rainy season rainfall statistics by pentad |
| Plague history | Infestation rate in prior seasons, spatial neighbors |
| Lot characteristics | Variety, soil group, humidity zone, crop cut number |
| Spatial | Buffer intersection with past infestation zones |

All features are computed via SQL and assembled into a single parquet dataset. Python handles diagnostics, validation, and the training pipeline.

## Repository Structure

```text
sql/model1_january/   SQL feature recipes — one file per feature group
scripts/              Dataset builders, diagnostics, data loaders
training/             Training pipeline (cross-validation, tuning, calibration)
docker/               Dockerfile for the training image
ec2/                  Scripts to launch and monitor remote training on AWS EC2
terraform/            Infrastructure as code — EC2 instance, security group, key pair
```

## Training Pipeline

The pipeline is config-driven and runs inside Docker. A single execution covers one stage:

```
diagnostics  →  class balance, feature coverage, fold viability
baseline     →  walk-forward CV with default hyperparameters
optuna       →  Bayesian hyperparameter search (N trials, stability-penalized objective)
```

All experiments are tracked with **MLflow**: fold metrics, OOF summaries, best hyperparameters, calibration parameters, and artifacts.

## Infrastructure

Training runs on an AWS EC2 instance (m5.xlarge) provisioned with Terraform. The training image is built locally and pushed to Amazon ECR. The dataset and all output artifacts are stored in S3.

```
Local → Docker build → ECR push
EC2   → docker pull → run container → artifacts → S3
```

## Tech Stack

Python · LightGBM · XGBoost · CatBoost · Optuna · SHAP · MLflow · Docker · AWS (EC2, ECR, S3, IAM) · Terraform · PostgreSQL

## Status

Model 1 January — v001 dataset built. Running diagnostics before baseline evaluation.
