#!/usr/bin/env bash
set -Eeuo pipefail

STAGE=""
MODEL=""
DATASET="${CHINCHE_DATASET:-chinche_ml_dataset}"
IMAGE="${CHINCHE_IMAGE:-chinche-training:latest}"
BUCKET="${CHINCHE_BUCKET:-eagriculturai-chinche}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
WORK_ROOT="${CHINCHE_WORK_ROOT:-$HOME/chinche-training}"
CPUS="${CHINCHE_CPUS:-4}"
MEMORY="${CHINCHE_MEMORY:-14g}"
SHM_SIZE="${CHINCHE_SHM_SIZE:-2g}"
INSTANCE_ID="${CHINCHE_INSTANCE_ID:-}"
INSTANCE_TYPE="${CHINCHE_INSTANCE_TYPE:-unknown}"
TARGET_COLUMN="${CHINCHE_TARGET_COLUMN:-target}"
PERIOD_COLUMN="${CHINCHE_PERIOD_COLUMN:-zafra}"
DATE_COLUMN="${CHINCHE_DATE_COLUMN:-prediction_date}"
ROW_ID_COLUMN="${CHINCHE_ROW_ID_COLUMN:-record_id}"
TRAIN_PERIODS="${CHINCHE_TRAIN_PERIODS:-}"
EVALUATION_PERIODS="${CHINCHE_EVALUATION_PERIODS:-}"
SCORING_PERIODS="${CHINCHE_SCORING_PERIODS:-}"
CATEGORICAL_COLUMNS="${CHINCHE_CATEGORICAL_COLUMNS:-}"
METADATA_COLUMNS="${CHINCHE_METADATA_COLUMNS:-}"
FORBIDDEN_COLUMNS="${CHINCHE_FORBIDDEN_COLUMNS:-}"
EXCLUDE_FEATURES="${CHINCHE_EXCLUDE_FEATURES:-}"
IMBALANCE="${CHINCHE_IMBALANCE:-balanced}"
OBJECTIVE_METRIC="${CHINCHE_OBJECTIVE_METRIC:-average_precision}"
THRESHOLD_STRATEGY="${CHINCHE_THRESHOLD_STRATEGY:-fixed}"
FIXED_THRESHOLD="${CHINCHE_FIXED_THRESHOLD:-0.5}"
MINIMUM_RECALL="${CHINCHE_MINIMUM_RECALL:-0.85}"
CALIBRATION="${CHINCHE_CALIBRATION:-none}"
OPTUNA_TRIALS=20
EARLY_STOPPING_ROUNDS=50
SHAP=true
REFRESH_DATASET=false
SKIP_PULL=false
SKIP_UPLOAD=false
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage:
  bash ec2/run_training.sh <diagnostics|baseline|optuna> [options]

Core options:
  --model MODEL              lightgbm, xgboost, or catboost.
                             Required for baseline/optuna; forbidden for diagnostics.
  --dataset NAME             S3 dataset key without .parquet.
  --image URI                Docker image URI.
  --bucket NAME              S3 bucket.
  --region REGION            AWS region.
  --instance-id ID           Existing EC2 instance ID, recorded in manifest.
  --instance-type TYPE       Host type, recorded in manifest.
  --cpus N                   Docker CPU limit.
  --memory SIZE              Docker memory limit.
  --shm-size SIZE            Docker shared-memory size.
  --train-periods CSV
  --evaluation-periods CSV
  --scoring-periods CSV
  --categorical-columns CSV
  --metadata-columns CSV
  --forbidden-columns CSV
  --exclude-features CSV
  --objective-metric NAME    average_precision, roc_auc, f2, or recall.
  --optuna-trials N
  --threshold-strategy NAME  fixed, f2, or recall_constraint.
  --fixed-threshold N
  --minimum-recall N
  --calibration NAME         none, sigmoid, or isotonic.
  --no-shap
  --refresh-dataset
  --skip-pull
  --skip-upload
  --dry-run

Exactly one stage and, for training stages, one model run per command.
The runner never advances automatically.
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"; }

while (($#)); do
    case "$1" in
        diagnostics|baseline|optuna)
            [[ -z "$STAGE" ]] || die "Only one stage may be selected"
            STAGE="$1"; shift ;;
        --model) MODEL="${2:?Missing --model value}"; shift 2 ;;
        --dataset) DATASET="${2:?Missing --dataset value}"; shift 2 ;;
        --image) IMAGE="${2:?Missing --image value}"; shift 2 ;;
        --bucket) BUCKET="${2:?Missing --bucket value}"; shift 2 ;;
        --region) AWS_REGION="${2:?Missing --region value}"; shift 2 ;;
        --work-root) WORK_ROOT="${2:?Missing --work-root value}"; shift 2 ;;
        --instance-id) INSTANCE_ID="${2:?Missing --instance-id value}"; shift 2 ;;
        --instance-type) INSTANCE_TYPE="${2:?Missing --instance-type value}"; shift 2 ;;
        --cpus) CPUS="${2:?Missing --cpus value}"; shift 2 ;;
        --memory) MEMORY="${2:?Missing --memory value}"; shift 2 ;;
        --shm-size) SHM_SIZE="${2:?Missing --shm-size value}"; shift 2 ;;
        --train-periods) TRAIN_PERIODS="${2:?Missing value}"; shift 2 ;;
        --evaluation-periods) EVALUATION_PERIODS="${2:?Missing value}"; shift 2 ;;
        --scoring-periods) SCORING_PERIODS="${2:?Missing value}"; shift 2 ;;
        --categorical-columns) CATEGORICAL_COLUMNS="${2:?Missing value}"; shift 2 ;;
        --metadata-columns) METADATA_COLUMNS="${2:?Missing value}"; shift 2 ;;
        --forbidden-columns) FORBIDDEN_COLUMNS="${2:?Missing value}"; shift 2 ;;
        --exclude-features) EXCLUDE_FEATURES="${2:?Missing value}"; shift 2 ;;
        --objective-metric) OBJECTIVE_METRIC="${2:?Missing value}"; shift 2 ;;
        --optuna-trials) OPTUNA_TRIALS="${2:?Missing value}"; shift 2 ;;
        --threshold-strategy) THRESHOLD_STRATEGY="${2:?Missing value}"; shift 2 ;;
        --fixed-threshold) FIXED_THRESHOLD="${2:?Missing value}"; shift 2 ;;
        --minimum-recall) MINIMUM_RECALL="${2:?Missing value}"; shift 2 ;;
        --calibration) CALIBRATION="${2:?Missing value}"; shift 2 ;;
        --no-shap) SHAP=false; shift ;;
        --refresh-dataset) REFRESH_DATASET=true; shift ;;
        --skip-pull) SKIP_PULL=true; shift ;;
        --skip-upload) SKIP_UPLOAD=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

[[ -n "$STAGE" ]] || { usage; die "A stage is required"; }
[[ -n "$TRAIN_PERIODS" ]] || die "Training periods must be configured"
if [[ "$STAGE" == "diagnostics" ]]; then
    [[ -z "$MODEL" ]] || die "Diagnostics is model-independent; omit --model"
else
    case "$MODEL" in lightgbm|xgboost|catboost) ;; *) die "A valid --model is required";; esac
fi

case "$STAGE" in
    diagnostics) MAX_RUNTIME_SECONDS=14400 ;;
    baseline) MAX_RUNTIME_SECONDS=14400 ;;
    optuna) MAX_RUNTIME_SECONDS=21600 ;;
esac

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MODEL_SLUG="${MODEL:-model-independent}"
RUN_ID="chinche-${DATASET//_/-}-${STAGE}-${MODEL_SLUG}-${TIMESTAMP}"
DATASET_DIR="$WORK_ROOT/datasets"
DATASET_PATH="$DATASET_DIR/$DATASET.parquet"
RUN_DIR="$WORK_ROOT/runs/$RUN_ID"
INPUT_DIR="$RUN_DIR/input"
OUTPUT_DIR="$RUN_DIR/output"
MODEL_DIR="$RUN_DIR/model"
LOG_DIR="$RUN_DIR/logs"
DATASET_S3_URI="s3://$BUCKET/datasets/$DATASET.parquet"
OUTPUT_S3_URI="s3://$BUCKET/experiments/$DATASET/$STAGE/$MODEL_SLUG/$RUN_ID/"
CONTAINER_NAME="chinche-training-active"
LOCK_FILE="$WORK_ROOT/training.lock"

ARGS=(
    --stage "$STAGE"
    --dataset "/opt/ml/input/data/train/$DATASET.parquet"
    --output-dir /opt/ml/output/data
    --model-dir /opt/ml/model
    --target-column "$TARGET_COLUMN"
    --period-column "$PERIOD_COLUMN"
    --date-column "$DATE_COLUMN"
    --row-id-column "$ROW_ID_COLUMN"
    --train-periods "$TRAIN_PERIODS"
    --evaluation-periods "$EVALUATION_PERIODS"
    --scoring-periods "$SCORING_PERIODS"
    --categorical-columns "$CATEGORICAL_COLUMNS"
    --metadata-columns "$METADATA_COLUMNS"
    --forbidden-columns "$FORBIDDEN_COLUMNS"
    --exclude-features "$EXCLUDE_FEATURES"
    --imbalance "$IMBALANCE"
    --objective-metric "$OBJECTIVE_METRIC"
    --threshold-strategy "$THRESHOLD_STRATEGY"
    --fixed-threshold "$FIXED_THRESHOLD"
    --minimum-recall "$MINIMUM_RECALL"
    --calibration "$CALIBRATION"
    --optuna-trials "$OPTUNA_TRIALS"
    --early-stopping-rounds "$EARLY_STOPPING_ROUNDS"
)
[[ -z "$MODEL" ]] || ARGS+=(--model "$MODEL")
$SHAP || ARGS+=(--no-shap)

DOCKER_COMMAND=(
    docker run --rm
    --name "$CONTAINER_NAME"
    --cpus "$CPUS"
    --memory "$MEMORY"
    --memory-swap "$MEMORY"
    --shm-size "$SHM_SIZE"
    -v "$INPUT_DIR:/opt/ml/input/data/train:ro"
    -v "$OUTPUT_DIR:/opt/ml/output/data"
    -v "$MODEL_DIR:/opt/ml/model"
    "$IMAGE"
    "${ARGS[@]}"
)

cat <<EOF
Run ID:          $RUN_ID
Stage:           $STAGE
Model:           ${MODEL:-<none>}
Dataset:         $DATASET_S3_URI
Image:           $IMAGE
EC2 instance:    ${INSTANCE_ID:-<not configured>} (${INSTANCE_TYPE})
Resources:       cpus=$CPUS memory=$MEMORY shm=$SHM_SIZE
Local run dir:   $RUN_DIR
Artifact target: $OUTPUT_S3_URI
EOF
printf 'Container command:'; printf ' %q' "${DOCKER_COMMAND[@]}"; printf '\n'
$DRY_RUN && exit 0

require_command aws
require_command docker
require_command flock
require_command timeout
mkdir -p "$DATASET_DIR" "$INPUT_DIR" "$OUTPUT_DIR" "$MODEL_DIR" "$LOG_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || die "Another run holds $LOCK_FILE"

if $REFRESH_DATASET || [[ ! -s "$DATASET_PATH" ]]; then
    aws s3 cp "$DATASET_S3_URI" "$DATASET_PATH.download" --region "$AWS_REGION"
    mv "$DATASET_PATH.download" "$DATASET_PATH"
fi
ln "$DATASET_PATH" "$INPUT_DIR/$DATASET.parquet" 2>/dev/null ||
    cp "$DATASET_PATH" "$INPUT_DIR/$DATASET.parquet"

if [[ "$IMAGE" == *.dkr.ecr.*.amazonaws.com/* ]] && ! $SKIP_PULL; then
    REGISTRY="${IMAGE%%/*}"
    aws ecr get-login-password --region "$AWS_REGION" |
        docker login --username AWS --password-stdin "$REGISTRY"
fi
$SKIP_PULL || docker pull "$IMAGE"

cat >"$RUN_DIR/run_manifest.json" <<EOF
{
  "run_id": "$RUN_ID",
  "stage": "$STAGE",
  "model": "$MODEL",
  "dataset_s3_uri": "$DATASET_S3_URI",
  "output_s3_uri": "$OUTPUT_S3_URI",
  "image": "$IMAGE",
  "instance_id": "$INSTANCE_ID",
  "instance_type": "$INSTANCE_TYPE",
  "cpus": "$CPUS",
  "memory": "$MEMORY",
  "shm_size": "$SHM_SIZE"
}
EOF

set +e
timeout --signal=TERM --kill-after=60 "$MAX_RUNTIME_SECONDS" \
    "${DOCKER_COMMAND[@]}" 2>&1 | tee "$LOG_DIR/training.log"
RUN_EXIT=${PIPESTATUS[0]}
set -e

cat >"$RUN_DIR/run_status.json" <<EOF
{"run_id":"$RUN_ID","exit_code":$RUN_EXIT,"finished_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF

if ! $SKIP_UPLOAD; then
    aws s3 cp "$OUTPUT_DIR" "${OUTPUT_S3_URI}output/" --recursive --region "$AWS_REGION"
    aws s3 cp "$MODEL_DIR" "${OUTPUT_S3_URI}model/" --recursive --region "$AWS_REGION"
    aws s3 cp "$LOG_DIR" "${OUTPUT_S3_URI}logs/" --recursive --region "$AWS_REGION"
    aws s3 cp "$RUN_DIR/run_manifest.json" "${OUTPUT_S3_URI}run_manifest.json" --region "$AWS_REGION"
    aws s3 cp "$RUN_DIR/run_status.json" "${OUTPUT_S3_URI}run_status.json" --region "$AWS_REGION"
fi

echo "Run finished: $RUN_ID"
echo "Local artifacts: $RUN_DIR"
exit "$RUN_EXIT"

