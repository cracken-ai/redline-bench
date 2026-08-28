#!/usr/bin/env bash
# Evaluate the dated DeepSeek V4 snapshots on RedLineBench via OpenRouter.
# Judges: Bedrock Sonnet 4.6 (s46) + OpenRouter DeepSeek V4 Pro (ds), same as the reference set.
#
# Prereqs:
#   export OPENROUTER_API_KEY=...   (model under test + hosted judge)
#   AWS creds in env                (Bedrock judge)
set -euo pipefail
cd "$(dirname "$0")"

PY="$(dirname "$0")/.venv/bin/python"
[ -x "$PY" ] || PY=python3

DATASET=data/benchmark.jsonl
OUT=results
OR="https://openrouter.ai/api/v1"
mkdir -p "$OUT"

: "${OPENROUTER_API_KEY:?export OPENROUTER_API_KEY before running}"

# label|openrouter slug
MODELS=(
  "DeepSeek-V4-Flash-0731|deepseek/deepseek-v4-flash-0731"
  "DeepSeek-V4-Pro-0813|deepseek/deepseek-v4-pro-0813"
)

for entry in "${MODELS[@]}"; do
  IFS='|' read -r LABEL SLUG <<<"$entry"

  echo "== GENERATE $LABEL =="
  "$PY" generate.py --dataset "$DATASET" \
    --output "$OUT/${LABEL}_model_outputs.jsonl" \
    --base-url "$OR" --model "$SLUG" --api-key "$OPENROUTER_API_KEY" --concurrency 16

  echo "== JUDGE $LABEL / s46 (Bedrock Sonnet 4.6) =="
  "$PY" run_judge.py \
    --model-outputs "$OUT/${LABEL}_model_outputs.jsonl" \
    --output "$OUT/${LABEL}__s46_rubric_verdicts.jsonl" \
    --provider bedrock --model us.anthropic.claude-sonnet-4-6 --region us-east-1 --concurrency 8

  echo "== JUDGE $LABEL / ds (OpenRouter DeepSeek V4 Pro) =="
  "$PY" run_judge.py \
    --model-outputs "$OUT/${LABEL}_model_outputs.jsonl" \
    --output "$OUT/${LABEL}__ds_rubric_verdicts.jsonl" \
    --provider openrouter --model deepseek/deepseek-v4-pro \
    --base-url "$OR" --api-key "$OPENROUTER_API_KEY" --concurrency 8
done

echo "== REPORT (all models in $OUT/) =="
"$PY" report.py "$OUT"
echo "Done."
