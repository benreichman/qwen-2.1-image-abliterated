#!/usr/bin/env bash
# A/B peak-memory + timing benchmark: base model vs Pruna turbo LoRA, same prompt/size/seed.
# Runs sd-cli directly (stop the backend's engine first so the two don't compete for memory).
# Usage: scripts/bench_memory.sh [width] [height] [outdir]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W="${1:-512}"; H="${2:-512}"; OUT="${3:-$ROOT/outputs/bench}"
mkdir -p "$OUT"
PROMPT='A glowing neon shop sign that reads "QWEN IMAGE 2.1", mounted on a brick wall in a narrow city alley at night. Heavy rain, wet pavement reflecting pink and blue light, shallow depth of field, cinematic photograph.'
COMMON=(--diffusion-model "$ROOT/models/diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf"
        --vae "$ROOT/models/vae/qwen_image_2.1_vae_bf16.safetensors"
        --llm "$ROOT/models/text_encoders/qwen3vl_8b_heretic-Q4_K_M.gguf"
        --lora-model-dir "$ROOT/models/loras"
        --diffusion-fa --sampling-method euler -W "$W" -H "$H" -s 42 -v)

run() {  # name, then sd-cli args
  local name="$1"; shift
  local log="$OUT/$name.log" peak=0 start
  start=$(date +%s)
  "$ROOT/engine/bin/sd-cli" "${COMMON[@]}" "$@" -o "$OUT/$name.png" > "$log" 2>&1 &
  local pid=$!
  # sample resident + phys_footprint (macOS) every second; keep the max
  while kill -0 "$pid" 2>/dev/null; do
    local fp
    fp=$(footprint -p "$pid" 2>/dev/null | awk '/phys_footprint/ {gsub(/[^0-9.]/,"",$2); print $2; exit}')
    local rss
    rss=$(ps -o rss= -p "$pid" 2>/dev/null | awk '{printf "%.0f", $1/1024}')
    [[ -n "$rss" && "$rss" -gt "$peak" ]] && peak=$rss
    sleep 1
  done
  wait "$pid"; local rc=$?
  local secs=$(( $(date +%s) - start ))
  echo "== $name: exit $rc, wall ${secs}s, peak RSS ${peak} MB"
  grep -E "params memory size|compute buffer|sampling completed|decode_first_stage completed|LoRA tensors|lora" "$log" | sed 's/^/   /' | head -20
}

echo "Benchmark ${W}x${H}, seed 42, outputs in $OUT"
run base  -p "$PROMPT" --steps 20 --cfg-scale 4.0
# LoRA via prompt tag (sd-cli syntax); :2 = multiplier 2.0 to reproduce PEFT alpha/r (see README)
run turbo -p "$PROMPT<lora:p_qwen_image_2.1_8step_v0.1:2>" --steps 8 --cfg-scale 1.0 \
          --sigmas "1,0.9333333,0.8571429,0.7692308,0.6666667,0.5454545,0.4,0.2222222,0"
