#!/usr/bin/env bash
# Evaluate Kimi K3 on RedLineBench via OpenRouter (hosted endpoint is already live).
# No GPU, no local serving. Judges: Bedrock Sonnet 4.6 + OpenRouter DeepSeek V4 Pro.
#
# Prereqs:
#   export OPENROUTER_API_KEY=...        (model under test + hosted judge)
#   AWS creds in env                     (Bedrock judge; drop the s46 judge if unavailable)
#
# Reference results for Kimi-K2.6 / DeepSeek-V4-Pro already exist in results/ for comparison.
set -euo pipefail
cd "$(dirname "$0")"

PY="$(dirname "$0")/.venv/bin/python"
[ -x "$PY" ] || PY=python3

DATASET=data/benchmark.jsonl
OUT=results
OR="https://openrouter.ai/api/v1"
mkdir -p "$OUT"

: "${OPENROUTER_API_KEY:?export OPENROUTER_API_KEY before running}"

LABEL="Kimi-K3"
MODEL_SLUG="moonshotai/kimi-k3"

echo "== GENERATE $LABEL =="
"$PY" generate.py --dataset "$DATASET" \
  --output "$OUT/${LABEL}_model_outputs.jsonl" \
  --base-url "$OR" --model "$MODEL_SLUG" --api-key "$OPENROUTER_API_KEY" --concurrency 16

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

echo "== REPORT (all models in $OUT/) =="
"$PY" report.py "$OUT"
echo "Done. Kimi-K3 vs the reference set (Kimi-K2.6 etc.) is in the tables above."
