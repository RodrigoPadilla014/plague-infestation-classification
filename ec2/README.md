# EC2 training runner

The runner executes exactly one stage:

```bash
bash ec2/run_training.sh diagnostics
bash ec2/run_training.sh baseline --model lightgbm
bash ec2/run_training.sh optuna --model catboost --optuna-trials 100
```

Copy `config.env.example` to `config.env`, adjust it, and source it before
running. Host selection and sizing are configuration values. The runner uses an
already-created EC2 host; it does not resize or create the instance.

Each run caches the parquet dataset, mounts isolated output/model directories,
records the instance and container settings, and uploads artifacts to:

```text
s3://<bucket>/experiments/<dataset>/<stage>/<model>/<run-id>/
```

Diagnostics is model-independent. Baseline and Optuna require exactly one of
LightGBM, XGBoost, or CatBoost.

